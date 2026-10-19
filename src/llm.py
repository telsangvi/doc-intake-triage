"""Model access, behind one interface.

Two ideas worth internalising here, both central to forward-deployed work:

1. The model is a swappable component, not the system. Everything else in
   this repo is written against `LLMClient`, so you can develop and test
   offline (MockLLM) and only pay for tokens when you want to.
2. The output contract matters more than the model. Every client returns
   the SAME dict shape, which `extract.py` turns into a validated object.
"""
from __future__ import annotations

import json
import re
from typing import Any, Protocol

from .config import settings
from .schemas import DocType


class LLMClient(Protocol):
    def extract_document(self, text: str, *, doc_types: list[str]) -> dict[str, Any]:
        """Return a dict shaped like schemas.Extraction."""
        ...


# --------------------------------------------------------------------------
# Mock client — deterministic, offline, no API key.
# It uses regexes so the whole project runs on any laptop with no network.
# It is a stand-in for a real model, not a replacement: your evals measure
# the harness with it, not model quality.
# --------------------------------------------------------------------------

_PLACEHOLDER_MARKERS = ("???", "unclear", "illegible", "n/a", "none", "unknown")

_FIELD_PATTERNS: dict[str, list[str]] = {
    "applicant_name": [r"applicant\s*name\s*[:\-]\s*(.+)", r"full\s*name\s*[:\-]\s*(.+)"],
    "date_of_birth": [r"date\s*of\s*birth\s*[:\-]\s*(.+)", r"\bdob\b\s*[:\-]\s*(.+)"],
    "address": [r"(?:residential\s*)?address\s*[:\-]\s*(.+)"],
    "benefit_type": [r"benefit\s*type\s*[:\-]\s*(.+)"],
    "monthly_income": [r"monthly\s*(?:household\s*)?income\s*[:\-]\s*(.+)", r"income\s*[:\-]\s*(.+)"],
    "patient_name": [r"patient\s*name\s*[:\-]\s*(.+)"],
    "provider_name": [r"(?:treating\s*provider|provider|physician|doctor)\s*[:\-]\s*(.+)"],
    "condition": [r"(?:condition|diagnosis)\s*[:\-]\s*(.+)"],
    "full_name": [r"full\s*name\s*[:\-]\s*(.+)"],
    "id_number": [r"id\s*number\s*[:\-]\s*(.+)"],
    "person_name": [r"(?:employee|person|name)\s*[:\-]\s*(.+)"],
    "income_amount": [r"(?:net\s*pay|income\s*amount|amount)\s*[:\-]\s*(.+)"],
    "period": [r"period\s*[:\-]\s*(.+)"],
}

_CLASSIFIER_KEYWORDS: dict[DocType, list[str]] = {
    DocType.BENEFIT_APPLICATION: ["application", "applicant name", "benefit type", "date received"],
    DocType.MEDICAL_EVIDENCE: ["hospital", "patient name", "diagnosis", "condition", "certify", "provider"],
    DocType.ID_PROOF: ["identity card", "id number", "issuing authority", "government"],
    DocType.INCOME_PROOF: ["salary slip", "net pay", "payslip", "income", "period"],
}


def _clean(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip().rstrip(".,;"))


class MockLLM:
    """Regex-based extractor used when provider == 'mock'."""

    def extract_document(self, text: str, *, doc_types: list[str]) -> dict[str, Any]:
        doc_type, type_conf = self._classify(text)
        fields: dict[str, dict[str, Any]] = {}
        for name, patterns in _FIELD_PATTERNS.items():
            value, confidence = self._grab(text, patterns)
            fields[name] = {"value": value, "confidence": confidence}

        found = [k for k, v in fields.items() if v["value"]]
        summary = (
            f"{doc_type.value}: extracted {len(found)} field(s) "
            f"({', '.join(found) if found else 'none'})."
        )
        return {
            "doc_type": doc_type.value,
            "doc_type_confidence": type_conf,
            "fields": fields,
            "summary": summary,
            "notes": ["offline mock extractor (no model call)"],
        }

    @staticmethod
    def _classify(text: str) -> tuple[DocType, float]:
        low = text.lower()
        best, best_score = DocType.UNKNOWN, 0.0
        for dtype, keywords in _CLASSIFIER_KEYWORDS.items():
            hits = sum(1 for kw in keywords if kw in low)
            score = hits / len(keywords)
            if score > best_score:
                best, best_score = dtype, score
        # Scale so a single strong signal is not mistaken for certainty.
        return best, round(min(best_score + 0.2, 0.95), 2) if best_score else 0.0

    @staticmethod
    def _grab(text: str, patterns: list[str]) -> tuple[str | None, float]:
        for pattern in patterns:
            match = re.search(pattern, text, flags=re.IGNORECASE)
            if not match:
                continue
            value = _clean(match.group(1))
            if not value:
                # Label present but blank (e.g. "Monthly Income:") -> missing.
                return None, 0.0
            if any(marker in value.lower() for marker in _PLACEHOLDER_MARKERS):
                return value, 0.35  # low confidence -> routed to a human
            return value, 0.9
        return None, 0.0


# --------------------------------------------------------------------------
# Real providers. Imported lazily so they are optional dependencies.
# --------------------------------------------------------------------------

_PROMPT = """You extract structured data from a case document for a public \
benefits office. Return ONLY a JSON object with this exact shape:
{{
  "doc_type": one of {doc_types},
  "doc_type_confidence": number 0-1,
  "fields": {{ "<field_name>": {{"value": <string|null>, "confidence": <0-1>}} }},
  "summary": "<one sentence>",
  "notes": ["<anything a human should double-check>"]
}}
Extract every field you can; use null for anything absent. Never invent values.

DOCUMENT:
\"\"\"
{text}
\"\"\"
"""


def _prompt(text: str, doc_types: list[str]) -> str:
    return _PROMPT.format(doc_types=doc_types, text=text[:12000])


def _parse_json(raw: str) -> dict[str, Any]:
    raw = raw.strip()
    raw = re.sub(r"^```(?:json)?|```$", "", raw, flags=re.MULTILINE).strip()
    return json.loads(raw)


class OpenAILLM:
    def __init__(self, model: str | None = None) -> None:
        from openai import OpenAI  # imported lazily

        self._client = OpenAI()
        self._model = model or settings.model

    def extract_document(self, text: str, *, doc_types: list[str]) -> dict[str, Any]:
        resp = self._client.chat.completions.create(
            model=self._model,
            messages=[{"role": "user", "content": _prompt(text, doc_types)}],
            response_format={"type": "json_object"},
            temperature=0,
        )
        return _parse_json(resp.choices[0].message.content or "{}")


class AnthropicLLM:
    def __init__(self, model: str | None = None) -> None:
        import anthropic  # imported lazily

        self._client = anthropic.Anthropic()
        self._model = model or settings.model

    def extract_document(self, text: str, *, doc_types: list[str]) -> dict[str, Any]:
        resp = self._client.messages.create(
            model=self._model,
            max_tokens=1024,
            messages=[{"role": "user", "content": _prompt(text, doc_types)}],
        )
        return _parse_json(resp.content[0].text)


def get_client(provider: str | None = None) -> LLMClient:
    """Factory. Defaults to whatever DOC_TRIAGE_PROVIDER says (mock)."""
    provider = (provider or settings.provider).lower()
    if provider == "mock":
        return MockLLM()
    if provider == "openai":
        return OpenAILLM()
    if provider == "anthropic":
        return AnthropicLLM()
    raise ValueError(f"Unknown provider: {provider!r}. Use mock|openai|anthropic.")
