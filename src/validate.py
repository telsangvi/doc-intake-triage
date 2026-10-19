"""Apply the office's rules to an extraction and decide what happens next.

Two distinct things are checked, and conflating them is a common mistake:

* Completeness  - are the fields the policy requires actually present?
* Confidence    - do we trust the values we did extract?

Completeness routes back to the applicant; confidence routes to a human.

The confidence check has two levels, which is what makes the routing
thresholds tunable (see `tuning.py`):
  * below `low`  -> the field is not trustworthy at all, flag the document
  * below `high` -> present and plausible, but not good enough to auto-route
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


def find_flags(extraction: Extraction, low: float | None = None) -> list[str]:
    low = settings.low_confidence_threshold if low is None else low
    flags: list[str] = []
    if extraction.doc_type == DocType.UNKNOWN:
        flags.append("unknown_doc_type")
    if extraction.doc_type_confidence < low:
        flags.append(f"low_type_confidence:{extraction.doc_type_confidence:.2f}")
    for name, fv in extraction.fields.items():
        if not fv.is_missing and fv.confidence < low:
            flags.append(f"low_confidence:{name}")
    return flags


def decide(
    extraction: Extraction,
    missing: list[str],
    flags: list[str],
    high: float | None = None,
) -> Decision:
    high = settings.high_confidence_threshold if high is None else high
    if missing:
        return Decision.INCOMPLETE
    if flags:
        return Decision.HUMAN_REVIEW
    # Everything required is present and above `low`. Auto-routing also
    # demands the required fields clear `high` — a wrong auto-route is worse
    # than sending the document to a person.
    for name in REQUIRED_FIELDS.get(extraction.doc_type, []):
        fv = extraction.fields.get(name)
        if fv is not None and not fv.is_missing and fv.confidence < high:
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
