"""End-to-end: the sample documents should route exactly as labelled."""
from pathlib import Path

from src.evals import run_evals
from src.llm import MockLLM
from src.pipeline import process_directory

DATA = Path(__file__).resolve().parent.parent / "data"


def test_pipeline_routes_samples():
    results = {r.source_file: r for r in process_directory(DATA / "samples", MockLLM())}
    assert results["case_001_application.txt"].decision.value == "auto_route"
    assert results["case_002_application.txt"].decision.value == "incomplete"
    assert "monthly_income" in results["case_002_application.txt"].missing_fields
    assert results["case_003_application.txt"].decision.value == "human_review"


def test_evals_reach_full_accuracy_on_gold_set():
    metrics = run_evals(DATA / "samples", DATA / "labels.jsonl", MockLLM())
    assert metrics["doc_type_accuracy"] == 1.0
    assert metrics["decision_accuracy"] == 1.0
    assert metrics["field_accuracy"] == 1.0
