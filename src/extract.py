"""Run one document through the model and normalise the result.

This is the seam between "whatever the model returned" and "the typed
object the rest of the system trusts".
"""
from __future__ import annotations

from typing import Any

from .llm import LLMClient
from .schemas import DocType, Extraction, FieldValue


def extract_document(text: str, client: LLMClient) -> Extraction:
    raw = client.extract_document(text, doc_types=[t.value for t in DocType])
    return normalise(raw)


def normalise(raw: dict[str, Any]) -> Extraction:
    """Coerce a model's raw dict into a validated Extraction.

    Defensive on purpose: models return slightly different shapes, and a
    forward-deployed system must not crash on one odd field.
    """
    try:
        doc_type = DocType(str(raw.get("doc_type", "unknown")).lower())
    except ValueError:
        doc_type = DocType.UNKNOWN

    fields: dict[str, FieldValue] = {}
    for name, payload in (raw.get("fields") or {}).items():
        if isinstance(payload, dict):
            fields[name] = FieldValue(
                value=payload.get("value"),
                confidence=float(payload.get("confidence") or 0.0),
            )
        else:  # model returned a bare value
            fields[name] = FieldValue(value=str(payload), confidence=0.5)

    return Extraction(
        doc_type=doc_type,
        doc_type_confidence=float(raw.get("doc_type_confidence") or 0.0),
        fields=fields,
        summary=str(raw.get("summary") or ""),
        notes=[str(n) for n in (raw.get("notes") or [])],
    )
