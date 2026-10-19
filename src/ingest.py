"""Turn a file on disk into plain text.

Real intake is messy: PDFs, scans, exports, plain text. This module hides
that behind one function so the rest of the pipeline never has to care.
"""
from __future__ import annotations

from pathlib import Path

TEXT_SUFFIXES = {".txt", ".md", ".text", ".log"}


def read_document(path: str | Path) -> str:
    """Return the text of a document. Raises FileNotFoundError if absent."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(path)

    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return _read_pdf(path)
    if suffix in TEXT_SUFFIXES:
        return path.read_text(encoding="utf-8", errors="replace")

    # Unknown suffix: best-effort text read.
    return path.read_text(encoding="utf-8", errors="replace")


def _read_pdf(path: Path) -> str:
    from pypdf import PdfReader

    reader = PdfReader(str(path))
    return "\n".join((page.extract_text() or "") for page in reader.pages)


def iter_documents(directory: str | Path) -> list[Path]:
    """All processable documents in a directory, sorted for stable runs."""
    directory = Path(directory)
    exts = TEXT_SUFFIXES | {".pdf"}
    return sorted(p for p in directory.iterdir() if p.is_file() and p.suffix.lower() in exts)
