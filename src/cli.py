"""Command-line entry points.

    python -m src.cli run data/samples      # process and print a queue
    python -m src.cli eval                  # score against the gold set
"""
from __future__ import annotations

import argparse
from collections import Counter
from pathlib import Path

from .evals import print_scorecard, run_evals
from .llm import get_client
from .pipeline import process_directory, process_file


def cmd_run(args: argparse.Namespace) -> int:
    client = get_client(args.provider)
    path = Path(args.path)
    if path.is_file():
        results = [process_file(path, client)]
    else:
        results = process_directory(path, client)

    print(f"\nProcessed {len(results)} document(s) with provider={client.__class__.__name__}\n")
    header = f"{'file':<32}{'doc_type':<22}{'decision':<15}missing"
    print(header)
    print("-" * len(header))
    for r in results:
        missing = ",".join(r.missing_fields) or "-"
        print(f"{r.source_file:<32}{r.extraction.doc_type.value:<22}{r.decision.value:<15}{missing}")

    counts = Counter(r.decision.value for r in results)
    print("\nRouting summary:", dict(counts))

    review = [r for r in results if r.decision.value != "auto_route"]
    if review:
        print("\nNeeds attention:")
        for r in review:
            print(f"  - {r.source_file}: {r.rationale}")
    print()
    return 0


def cmd_eval(args: argparse.Namespace) -> int:
    client = get_client(args.provider)
    metrics = run_evals(args.samples, args.labels, client)
    print_scorecard(metrics)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="doc-intake-triage")
    parser.add_argument("--provider", default=None, help="mock | openai | anthropic")
    sub = parser.add_subparsers(dest="command", required=True)

    run_p = sub.add_parser("run", help="process documents into a review queue")
    run_p.add_argument("path", help="a file or a directory of documents")
    run_p.set_defaults(func=cmd_run)

    eval_p = sub.add_parser("eval", help="score extraction against a labelled gold set")
    eval_p.add_argument("--samples", default="data/samples")
    eval_p.add_argument("--labels", default="data/labels.jsonl")
    eval_p.set_defaults(func=cmd_eval)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
