"""Retrieval over the office's policy corpus (the "RAG" half).

Why this exists: a routing decision that says "missing income" is only useful
to a caseworker if it can also say *which rule* it applied. Retrieval grounds
the decision in the customer's own policy documents and makes it citable.

Design notes that matter in a real deployment:
  * The embedder is swappable, like the LLM. `HashingEmbedder` runs offline
    with no network and no model, so the whole project still runs on a laptop.
    Swap in a real embedding model for production quality.
  * Passages are chunked on headings, so each chunk keeps its clause id. A
    citation without a clause id is not auditable.
"""
from __future__ import annotations

import hashlib
import math
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Protocol

from .config import settings

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_POLICY_DIR = PROJECT_ROOT / "data" / "policy"


class Embedder(Protocol):
    def embed(self, texts: list[str]) -> list[list[float]]:
        ...


def _tokenize(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", text.lower())


class HashingEmbedder:
    """Offline bag-of-words hashing embedder. Deterministic, no network.

    Not a semantic embedder — it matches on vocabulary, not meaning. That is
    enough to demonstrate the retrieval seam, and it is honest about being a
    stand-in: swap it for a real embedding model before you trust the ranking.
    """

    def __init__(self, dim: int | None = None) -> None:
        self.dim = dim or settings.embedding_dim

    def embed(self, texts: list[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        for text in texts:
            vec = [0.0] * self.dim
            for token in _tokenize(text):
                idx = int(hashlib.md5(token.encode()).hexdigest(), 16) % self.dim
                vec[idx] += 1.0
            norm = math.sqrt(sum(x * x for x in vec)) or 1.0
            vectors.append([x / norm for x in vec])
        return vectors


class OpenAIEmbedder:
    """Real embeddings, imported lazily so it stays optional."""

    def __init__(self, model: str = "text-embedding-3-small") -> None:
        from openai import OpenAI

        self._client = OpenAI()
        self._model = model

    def embed(self, texts: list[str]) -> list[list[float]]:
        resp = self._client.embeddings.create(model=self._model, input=texts)
        return [item.embedding for item in resp.data]


@dataclass
class Passage:
    id: str
    source: str
    clause: str
    text: str


def chunk_markdown(text: str, source: str) -> list[Passage]:
    """Split on '## ' headings so each passage keeps its clause id."""
    passages: list[Passage] = []
    current_clause = source
    buffer: list[str] = []

    def flush() -> None:
        body = "\n".join(buffer).strip()
        if body:
            pid = f"{source}#{len(passages)}"
            passages.append(Passage(id=pid, source=source, clause=current_clause, text=body))

    for line in text.splitlines():
        if line.startswith("## "):
            flush()
            current_clause = line[3:].strip()
            buffer = [line[3:].strip()]
        elif line.startswith("# "):
            continue  # document title; clause comes from the ## heading
        else:
            buffer.append(line)
    flush()
    return passages


class Retriever:
    def __init__(self, passages: list[Passage], embedder: Embedder | None = None) -> None:
        self.passages = passages
        self.embedder = embedder or HashingEmbedder()
        self._vectors = self.embedder.embed([p.text for p in passages]) if passages else []

    @property
    def size(self) -> int:
        return len(self.passages)

    def search(self, query: str, k: int = 3) -> list[tuple[float, Passage]]:
        if not self.passages:
            return []
        qv = self.embedder.embed([query])[0]
        scored = [
            (sum(a * b for a, b in zip(qv, vec)), passage)
            for vec, passage in zip(self._vectors, self.passages)
        ]
        scored.sort(key=lambda item: item[0], reverse=True)
        return [(score, p) for score, p in scored[:k] if score > 0]


def build_index(policy_dir: str | Path = DEFAULT_POLICY_DIR) -> Retriever:
    policy_dir = Path(policy_dir)
    passages: list[Passage] = []
    if policy_dir.exists():
        for path in sorted(policy_dir.glob("*.md")):
            passages.extend(chunk_markdown(path.read_text(encoding="utf-8"), path.name))
    return Retriever(passages)


class SupabaseRetriever:
    """Postgres + pgvector backend (Supabase).

    Same `search` contract as the in-memory `Retriever`, so the pipeline never
    knows which one it is talking to. The connection string comes from the
    environment — never hardcode it, and never commit it.
    """

    def __init__(
        self,
        dsn: str | None = None,
        embedder: Embedder | None = None,
        function: str = "triage.match_policy_passages",
        table: str = "triage.policy_passages",
    ) -> None:
        self.dsn = dsn or settings.supabase_db_url
        if not self.dsn:
            raise RuntimeError(
                "SUPABASE_DB_URL is not set. To use the Supabase backend, set "
                "RETRIEVER_BACKEND=supabase and SUPABASE_DB_URL=<postgres dsn>."
            )
        self.embedder = embedder or HashingEmbedder()
        self.function = function
        self.table = table

    def _connect(self):
        import psycopg  # optional dependency, imported lazily

        return psycopg.connect(self.dsn)

    def search(self, query: str, k: int = 3) -> list[tuple[float, Passage]]:
        vector = "[" + ",".join(f"{x:.5f}" for x in self.embedder.embed([query])[0]) + "]"
        sql = (
            "select id, source, clause, content, similarity "
            f"from {self.function}(%s::extensions.vector, %s)"
        )
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(sql, (vector, k))
            rows = cur.fetchall()
        return [
            (float(sim), Passage(id=rid, source=src, clause=clause, text=content))
            for rid, src, clause, content, sim in rows
        ]

    @property
    def size(self) -> int:
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(f"select count(*) from {self.table}")
            return int(cur.fetchone()[0])


def build_retriever(backend: str | None = None) -> Retriever | SupabaseRetriever:
    """Pick the vector-store backend from config. Defaults to the offline one."""
    backend = (backend or settings.retriever_backend).lower()
    if backend == "supabase":
        return SupabaseRetriever()
    if backend == "memory":
        return build_index()
    raise ValueError(f"Unknown retriever backend: {backend!r}. Use memory|supabase.")


@lru_cache(maxsize=1)
def default_retriever() -> Retriever | SupabaseRetriever:
    """Cached retriever for the configured backend."""
    return build_retriever()
