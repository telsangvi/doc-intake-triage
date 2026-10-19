"""Orchestration: files in, a review queue out."""
from __future__ import annotations

import re
from pathlib import Path

from .extract import extract_document
from .ingest import iter_documents, read_document
from .llm import LLMClient, get_client
from .retrieve import Retriever, default_retriever
from .schemas import CaseResult, Extraction, PolicyRef
from .validate import build_rationale, decide, find_flags, find_missing


def case_id_from_filename(name: str) -> str:
    """case_001_application.txt -> case_001 (falls back to the stem)."""
    match = re.match(r"(case[_-]?\d+)", name, flags=re.IGNORECASE)
    return match.group(1).lower() if match else Path(name).stem


def _policy_query(extraction: Extraction, missing: list[str], flags: list[str]) -> str:
    """Build the retrieval query from what the decision actually turned on."""
    parts = [extraction.doc_type.value.replace("_", " ")]
    parts += [m.replace("_", " ") for m in missing]
    benefit = extraction.fields.get("benefit_type")
    if benefit and benefit.value:
        parts.append(benefit.value)
    parts += [f.split(":")[0].replace("_", " ") for f in flags]
    return " ".join(parts)


def _policy_refs(query: str, retriever: Retriever | None, k: int = 2) -> list[PolicyRef]:
    if retriever is None:
        return []
    refs: list[PolicyRef] = []
    for score, passage in retriever.search(query, k=k):
        refs.append(
            PolicyRef(
                clause=passage.clause,
                source=passage.source,
                text=passage.text[:400],
                score=round(score, 3),
            )
        )
    return refs


def process_file(
    path: str | Path,
    client: LLMClient | None = None,
    retriever: Retriever | None = None,
    low: float | None = None,
    high: float | None = None,
) -> CaseResult:
    client = client or get_client()
    path = Path(path)
    text = read_document(path)
    extraction = extract_document(text, client)

    missing = find_missing(extraction)
    flags = find_flags(extraction, low=low)
    decision = decide(extraction, missing, flags, high=high)
    rationale = build_rationale(extraction, missing, flags)

    refs = _policy_refs(_policy_query(extraction, missing, flags), retriever)
    if refs:
        rationale = f"{rationale} Applies {refs[0].clause}."

    return CaseResult(
        case_id=case_id_from_filename(path.name),
        source_file=path.name,
        extraction=extraction,
        missing_fields=missing,
        flags=flags,
        decision=decision,
        rationale=rationale,
        policy_refs=refs,
    )


def process_directory(
    directory: str | Path,
    client: LLMClient | None = None,
    retriever: Retriever | None = None,
    low: float | None = None,
    high: float | None = None,
) -> list[CaseResult]:
    client = client or get_client()
    if retriever is None:
        retriever = default_retriever()
    return [
        process_file(p, client, retriever, low=low, high=high)
        for p in iter_documents(directory)
    ]
