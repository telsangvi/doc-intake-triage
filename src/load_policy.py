"""Load the policy corpus into the Supabase vector store.

Run this after applying `sql/001_triage_policy_passages.sql` and after any
change to the policy documents, so the index matches the corpus.

    RETRIEVER_BACKEND=supabase SUPABASE_DB_URL=postgresql://... \
        python -m src.cli load-policy

The connection string is read from the environment only. Do not put it in the
repo or in a commit.
"""
from __future__ import annotations

from pathlib import Path

from .config import settings
from .retrieve import DEFAULT_POLICY_DIR, HashingEmbedder, chunk_markdown


def load_policy_into_supabase(
    policy_dir: str | Path = DEFAULT_POLICY_DIR,
    dsn: str | None = None,
    table: str = "triage.policy_passages",
) -> int:
    """Embed every policy passage and upsert it. Idempotent by primary key."""
    import psycopg  # optional dependency, imported lazily

    dsn = dsn or settings.supabase_db_url
    if not dsn:
        raise RuntimeError(
            "SUPABASE_DB_URL is not set. Export it before loading the corpus."
        )

    embedder = HashingEmbedder()
    passages = []
    for path in sorted(Path(policy_dir).glob("*.md")):
        passages.extend(chunk_markdown(path.read_text(encoding="utf-8"), path.name))
    vectors = embedder.embed([p.text for p in passages])

    sql = (
        f"insert into {table} (id, source, clause, content, embedding) "
        "values (%s, %s, %s, %s, %s::extensions.vector) "
        "on conflict (id) do update set "
        "source = excluded.source, clause = excluded.clause, "
        "content = excluded.content, embedding = excluded.embedding"
    )
    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        for passage, vector in zip(passages, vectors):
            literal = "[" + ",".join(f"{x:.5f}" for x in vector) + "]"
            cur.execute(sql, (passage.id, passage.source, passage.clause,
                              passage.text, literal))
        conn.commit()
    return len(passages)
