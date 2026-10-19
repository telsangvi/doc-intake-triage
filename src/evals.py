"""The evaluation harness.

This is the part that separates a demo from a deployment. Every FDE job
description names evaluation explicitly; a project that ships an eval
scorecard is worth more than ten that only ship a demo.

It answers three questions against a labelled gold set:
  * did we classify the document correctly?
  * did we extract the right values?
  * did we route it the way a human would?
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from .llm import LLMClient, get_client
from .pipeline import process_directory


def _norm(value: object) -> str:
    """Loose comparison: case, spacing and trailing punctuation don't matter."""
    text = "" if value is None else str(value)
    text = re.sub(r"\s+", " ", text.strip().lower())
    return text.rstrip(".,;")


def load_labels(labels_path: str | Path) -> list[dict]:
    lines = Path(labels_path).read_text(encoding="utf-8").splitlines()
    return [json.loads(line) for line in lines if line.strip()]


def run_evals(
    samples_dir: str | Path,
    labels_path: str | Path,
    client: LLMClient | None = None,
) -> dict:
    client = client or get_client()
    labels = load_labels(labels_path)
    results = {r.source_file: r for r in process_directory(samples_dir, client)}

    type_hits = type_total = 0
    decision_hits = decision_total = 0
    field_hits = field_total = 0
    field_errors: list[str] = []
    missing_results: list[str] = []

    for gold in labels:
        result = results.get(gold["file"])
        if result is None:
            missing_results.append(gold["file"])
            continue

        type_total += 1
        if result.extraction.doc_type.value == gold["doc_type"]:
            type_hits += 1

        decision_total += 1
        if result.decision.value == gold["decision"]:
            decision_hits += 1

        for name, expected in gold.get("fields", {}).items():
            field_total += 1
            actual = result.extraction.fields.get(name)
            if actual and _norm(actual.value) == _norm(expected):
                field_hits += 1
            else:
                got = actual.value if actual else None
                field_errors.append(f"{gold['file']}:{name} expected={expected!r} got={got!r}")

    def ratio(hit: int, total: int) -> float:
        return round(hit / total, 3) if total else 0.0

    return {
        "documents": len(labels),
        "doc_type_accuracy": ratio(type_hits, type_total),
        "decision_accuracy": ratio(decision_hits, decision_total),
        "field_accuracy": ratio(field_hits, field_total),
        "counts": {
            "doc_type": [type_hits, type_total],
            "decision": [decision_hits, decision_total],
            "field": [field_hits, field_total],
        },
        "field_errors": field_errors,
        "missing_results": missing_results,
    }


def print_scorecard(metrics: dict) -> None:
    print("\n=== Eval scorecard ===")
    print(f"documents scored : {metrics['documents']}")
    print(f"doc-type accuracy: {metrics['doc_type_accuracy']:.0%}  {metrics['counts']['doc_type']}")
    print(f"decision accuracy: {metrics['decision_accuracy']:.0%}  {metrics['counts']['decision']}")
    print(f"field accuracy   : {metrics['field_accuracy']:.0%}  {metrics['counts']['field']}")
    if metrics["field_errors"]:
        print("\nField-level misses (these are your next prompt/eval iterations):")
        for err in metrics["field_errors"]:
            print(f"  - {err}")
    if metrics["missing_results"]:
        print(f"\nNo result produced for: {metrics['missing_results']}")
    print()
