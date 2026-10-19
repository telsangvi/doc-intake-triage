"""Routing logic is the cheapest thing to test and the easiest to get wrong."""
from src.llm import MockLLM
from src.schemas import Decision, DocType, Extraction, FieldValue
from src.validate import decide, find_flags, find_missing


def _complete_application() -> Extraction:
    fields = {
        "applicant_name": FieldValue(value="Ramesh Kumar", confidence=0.9),
        "date_of_birth": FieldValue(value="14/07/1985", confidence=0.9),
        "address": FieldValue(value="22 Gandhi Road", confidence=0.9),
        "benefit_type": FieldValue(value="Disability Allowance", confidence=0.9),
        "monthly_income": FieldValue(value="INR 18,500", confidence=0.9),
    }
    return Extraction(
        doc_type=DocType.BENEFIT_APPLICATION,
        doc_type_confidence=0.95,
        fields=fields,
    )


def test_complete_and_confident_auto_routes():
    ext = _complete_application()
    missing, flags = find_missing(ext), find_flags(ext)
    assert missing == []
    assert flags == []
    assert decide(ext, missing, flags) == Decision.AUTO_ROUTE


def test_missing_required_field_is_incomplete():
    ext = _complete_application()
    ext.fields["monthly_income"] = FieldValue(value=None, confidence=0.0)
    missing, flags = find_missing(ext), find_flags(ext)
    assert "monthly_income" in missing
    assert decide(ext, missing, flags) == Decision.INCOMPLETE


def test_low_confidence_routes_to_human():
    ext = _complete_application()
    ext.fields["applicant_name"] = FieldValue(value="???", confidence=0.35)
    missing, flags = find_missing(ext), find_flags(ext)
    assert missing == []
    assert any(f.startswith("low_confidence") for f in flags)
    assert decide(ext, missing, flags) == Decision.HUMAN_REVIEW


def test_medium_confidence_does_not_auto_route():
    """Present and above `low`, but below `high` -> a human, not a shortcut."""
    ext = _complete_application()
    ext.fields["applicant_name"] = FieldValue(value="R Kumar", confidence=0.7)
    missing, flags = find_missing(ext), find_flags(ext)
    assert flags == []  # 0.7 clears the low threshold
    assert decide(ext, missing, flags) == Decision.HUMAN_REVIEW


def test_unknown_doc_type_is_flagged():
    ext = Extraction(doc_type=DocType.UNKNOWN, doc_type_confidence=0.0, fields={})
    flags = find_flags(ext)
    assert "unknown_doc_type" in flags


def test_mock_classifies_a_medical_letter():
    text = "CITY GENERAL HOSPITAL\nPatient Name: A\nCondition: X\nThis is to certify."
    raw = MockLLM().extract_document(text, doc_types=["medical_evidence"])
    assert raw["doc_type"] == "medical_evidence"
