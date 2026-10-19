"""Apply the office's rules to an extraction and decide what happens next.

Two distinct things are checked, and conflating them is a common mistake:

* Completeness  - are the fields the policy requires actually present?
* Confidence    - do we trust the values we did extract?

Completeness routes back to the applicant; confidence routes to a human.
"""
from __future__ import annotations

from .config import settings
from .schemas import REQUIRED_FIELDS, Decision, DocType, Extraction


def find_missing(extraction: Extraction) -> list[str]:
    required = REQUIRED_FIELDS.get(extraction.doc_type, [])
    missing = []
    for name in required:
        fv = extraction.fields.get(name)
        if fv is None or fv.is_missing:
            missing.append(name)
    return missing


def find_flags(extraction: Extraction) -> list[str]:
    flags: list[str] = []
    if extraction.doc_type == DocType.UNKNOWN:
        flags.append("unknown_doc_type")
    if extraction.doc_type_confidence < settings.low_confidence_threshold:
        flags.append(f"low_type_confidence:{extraction.doc_type_confidence:.2f}")
    for name, fv in extraction.fields.items():
        if not fv.is_missing and fv.confidence < settings.low_confidence_threshold:
            flags.append(f"low_confidence:{name}")
    return flags


def decide(missing: list[str], flags: list[str]) -> Decision:
    if missing:
        return Decision.INCOMPLETE
    if flags:
        return Decision.HUMAN_REVIEW
    return Decision.AUTO_ROUTE


def build_rationale(extraction: Extraction, missing: list[str], flags: list[str]) -> str:
    if missing:
        return f"Missing required field(s): {', '.join(missing)}. Request from applicant."
    if flags:
        return f"Needs a human look: {', '.join(flags)}."
    return (
        f"All required fields present and confidence >= "
        f"{settings.high_confidence_threshold:.2f}."
    )
