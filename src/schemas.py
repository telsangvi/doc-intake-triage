"""The contract for everything the pipeline produces.

Defining the output shape first is a core forward-deployed habit: it is
the thing the customer's downstream system will depend on, and it is what
your evals score against.
"""
from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class DocType(str, Enum):
    BENEFIT_APPLICATION = "benefit_application"
    MEDICAL_EVIDENCE = "medical_evidence"
    ID_PROOF = "id_proof"
    INCOME_PROOF = "income_proof"
    UNKNOWN = "unknown"


class Decision(str, Enum):
    AUTO_ROUTE = "auto_route"        # complete and confident -> straight through
    HUMAN_REVIEW = "human_review"    # ambiguous or low confidence -> a person looks
    INCOMPLETE = "incomplete"        # required fields missing -> back to the applicant


class FieldValue(BaseModel):
    """A single extracted field plus how much we trust it."""

    value: str | None = None
    confidence: float = 0.0

    @property
    def is_missing(self) -> bool:
        return self.value is None or str(self.value).strip() == ""


class Extraction(BaseModel):
    """What the model returns for one document."""

    doc_type: DocType = DocType.UNKNOWN
    doc_type_confidence: float = 0.0
    fields: dict[str, FieldValue] = Field(default_factory=dict)
    summary: str = ""
    notes: list[str] = Field(default_factory=list)


class CaseResult(BaseModel):
    """One processed document, ready for the review queue."""

    case_id: str
    source_file: str
    extraction: Extraction
    missing_fields: list[str] = Field(default_factory=list)
    flags: list[str] = Field(default_factory=list)
    decision: Decision = Decision.HUMAN_REVIEW
    rationale: str = ""


# --- Policy: what a "complete" document of each type must contain. -------
# In a real engagement this table is written WITH the customer, because it
# encodes their rules, not yours.
REQUIRED_FIELDS: dict[DocType, list[str]] = {
    DocType.BENEFIT_APPLICATION: [
        "applicant_name",
        "date_of_birth",
        "address",
        "benefit_type",
        "monthly_income",
    ],
    DocType.MEDICAL_EVIDENCE: ["patient_name", "provider_name", "condition"],
    DocType.ID_PROOF: ["full_name", "id_number"],
    DocType.INCOME_PROOF: ["person_name", "income_amount", "period"],
}
