"""Orchestration: files in, a review queue out."""
from __future__ import annotations

import re
from pathlib import Path

from .extract import extract_document
from .ingest import iter_documents, read_document
from .llm import LLMClient, get_client
from .schemas import CaseResult
from .validate import build_rationale, decide, find_flags, find_missing


def case_id_from_filename(name: str) -> str:
    """case_001_application.txt -> case_001 (falls back to the stem)."""
    match = re.match(r"(case[_-]?\d+)", name, flags=re.IGNORECASE)
    return match.group(1).lower() if match else Path(name).stem


def process_file(path: str | Path, client: LLMClient | None = None) -> CaseResult:
    client = client or get_client()
    path = Path(path)
    text = read_document(path)
    extraction = extract_document(text, client)
    missing = find_missing(extraction)
    flags = find_flags(extraction)
    return CaseResult(
        case_id=case_id_from_filename(path.name),
        source_file=path.name,
        extraction=extraction,
        missing_fields=missing,
        flags=flags,
        decision=decide(missing, flags),
        rationale=build_rationale(extraction, missing, flags),
    )


def process_directory(directory: str | Path, client: LLMClient | None = None) -> list[CaseResult]:
    client = client or get_client()
    return [process_file(p, client) for p in iter_documents(directory)]
