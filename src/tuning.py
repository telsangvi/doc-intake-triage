"""Tuning, driven by the eval harness.

"Tuning" is three different jobs, and it is worth keeping them apart:

1. Routing-policy tuning — choosing the confidence thresholds. This is a
   business decision (how much risk of a wrong auto-route will the customer
   accept?), and it is measurable offline. `sweep_thresholds` does it.
2. Prompt / few-shot tuning — choosing how you ask the model. `PROMPT_VARIANTS`
   holds candidate templates; score them with the eval harness.
3. Fine-tuning — training a model on labelled examples. `export_finetune_dataset`
   writes the training file in provider format. It does NOT launch a job: that
   needs credentials and spends money, so it stays a deliberate manual step.

A note on the offline mock: it ignores the prompt entirely, so a prompt sweep
under `provider=mock` scores identically for every variant. That is not a bug —
it is the lesson. You cannot tune a model that does not read your prompt.
"""
from __future__ import annotations

import json
from pathlib import Path

from .extract import extract_document
from .evals import load_labels
from .ingest import read_document
from .llm import LLMClient, get_client
from .schemas import Decision
from .validate import decide, find_flags, find_missing

# Candidate prompt templates. Used by the real providers (OpenAILLM /
# AnthropicLLM); ignored by MockLLM. Score each with `run_evals`.
PROMPT_VARIANTS: dict[str, str] = {
    "baseline": "Extract the requested fields from the document. Return JSON only.",
    "schema_strict": (
        "Extract the requested fields. Return JSON only, using null for any "
        "field not present. Never guess a value. Set confidence below 0.6 when "
        "the source text is unclear or illegible."
    ),
    "few_shot": (
        "Extract the requested fields. Return JSON only. Examples: "
        "a field reading '???' is not a value — return null with confidence 0; "
        "a field reading 'unclear' is not a value — return null with confidence 0."
    ),
}

_SYSTEM_INSTRUCTION = (
    "You extract structured data from case documents for a public benefits "
    "office. Return a JSON object with keys doc_type, doc_type_confidence, "
    "fields, summary and notes. Use null for absent fields; never invent values."
)


def _extractions(samples_dir: str | Path, labels: list[dict], client: LLMClient):
    """Extract each labelled document once, so a sweep reuses the work."""
    out = []
    for gold in labels:
        path = Path(samples_dir) / gold["file"]
        if not path.exists():
            continue
        extraction = extract_document(read_document(path), client)
        out.append((gold, extraction))
    return out


def sweep_thresholds(
    samples_dir: str | Path,
    labels_path: str | Path,
    client: LLMClient | None = None,
    lows: list[float] | None = None,
    highs: list[float] | None = None,
) -> dict:
    """Grid-search the routing thresholds against the gold set.

    Reports decision accuracy alongside auto-route precision, because the two
    trade off: a conservative setting routes fewer documents but is rarely
    wrong, which is usually what a public-sector customer wants.
    """
    client = client or get_client()
    lows = lows or [0.4, 0.6, 0.8]
    highs = highs or [0.8, 0.9, 0.95]
    labels = load_labels(labels_path)
    docs = _extractions(samples_dir, labels, client)

    rows = []
    for low in lows:
        for high in highs:
            if high < low:
                continue
            correct = auto_total = auto_correct = 0
            for gold, extraction in docs:
                missing = find_missing(extraction)
                flags = find_flags(extraction, low=low)
                decision = decide(extraction, missing, flags, high=high)
                if decision.value == gold["decision"]:
                    correct += 1
                if decision == Decision.AUTO_ROUTE:
                    auto_total += 1
                    if gold["decision"] == "auto_route":
                        auto_correct += 1
            n = len(docs) or 1
            rows.append({
                "low": low,
                "high": high,
                "decision_accuracy": round(correct / n, 3),
                "auto_routed": auto_total,
                "auto_route_precision": round(auto_correct / auto_total, 3) if auto_total else 1.0,
            })

    best = max(rows, key=lambda r: (r["decision_accuracy"], r["auto_route_precision"]))
    return {"rows": rows, "best": best}


def print_sweep(result: dict) -> None:
    print("\n=== Routing threshold sweep ===")
    print(f"{'low':>5}{'high':>7}{'decision_acc':>14}{'auto_routed':>13}{'auto_precision':>16}")
    for r in result["rows"]:
        print(f"{r['low']:>5}{r['high']:>7}{r['decision_accuracy']:>14.0%}"
              f"{r['auto_routed']:>13}{r['auto_route_precision']:>16.0%}")
    b = result["best"]
    print(f"\nBest: low={b['low']} high={b['high']} "
          f"(decision {b['decision_accuracy']:.0%}, auto-route precision "
          f"{b['auto_route_precision']:.0%})\n")


def export_finetune_dataset(
    samples_dir: str | Path,
    labels_path: str | Path,
    out_path: str | Path,
) -> int:
    """Write a labelled training file in OpenAI chat fine-tune format.

    This is the artifact, not the job. To actually launch a fine-tune you would
    run (after reviewing the file and the cost):

        openai api fine_tuning.jobs.create \\
            -t <out_path> -m gpt-4o-mini-2024-07-18

    Nothing here calls a provider or spends money.
    """
    labels = load_labels(labels_path)
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    n = 0
    with out_path.open("w", encoding="utf-8") as fh:
        for gold in labels:
            path = Path(samples_dir) / gold["file"]
            if not path.exists():
                continue
            target = {
                "doc_type": gold["doc_type"],
                "doc_type_confidence": 0.95,
                "fields": {k: {"value": v, "confidence": 0.95}
                           for k, v in gold.get("fields", {}).items()},
                "summary": f"{gold['doc_type']} extracted from {gold['file']}.",
                "notes": [],
            }
            record = {
                "messages": [
                    {"role": "system", "content": _SYSTEM_INSTRUCTION},
                    {"role": "user", "content": read_document(path)},
                    {"role": "assistant", "content": json.dumps(target)},
                ]
            }
            fh.write(json.dumps(record) + "\n")
            n += 1
    return n
