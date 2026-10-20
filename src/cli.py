"""Command-line entry points.

    python -m src.cli run data/samples        # process and print a queue
    python -m src.cli eval                    # score against the gold set
    python -m src.cli tune                    # sweep routing thresholds
    python -m src.cli export-ft               # write a fine-tune dataset
    python -m src.cli retrieve "income evidence"   # inspect the policy index
"""
from __future__ import annotations

import argparse
from collections import Counter
from pathlib import Path

from .evals import print_scorecard, run_evals
from .llm import get_client
from .load_policy import load_policy_into_supabase
from .pipeline import process_directory, process_file
from .retrieve import default_retriever
from .tuning import export_finetune_dataset, print_sweep, sweep_thresholds


def cmd_run(args: argparse.Namespace) -> int:
    client = get_client(args.provider)
    retriever = default_retriever()
    path = Path(args.path)
    if path.is_file():
        results = [process_file(path, client, retriever)]
    else:
        results = process_directory(path, client, retriever)

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
            for ref in r.policy_refs[:1]:
                print(f"      policy {ref.clause} ({ref.source}, score {ref.score})")
    print()
    return 0


def cmd_eval(args: argparse.Namespace) -> int:
    client = get_client(args.provider)
    metrics = run_evals(args.samples, args.labels, client)
    print_scorecard(metrics)
    return 0


def cmd_tune(args: argparse.Namespace) -> int:
    client = get_client(args.provider)
    result = sweep_thresholds(args.samples, args.labels, client)
    print_sweep(result)
    return 0


def cmd_export(args: argparse.Namespace) -> int:
    n = export_finetune_dataset(args.samples, args.labels, args.out)
    print(f"\nWrote {n} training example(s) to {args.out}")
    print("This is the dataset only. Launching a fine-tune is a deliberate, "
          "paid step — see src/tuning.py for the command.\n")
    return 0


def cmd_retrieve(args: argparse.Namespace) -> int:
    retriever = default_retriever()
    print(f"\nPolicy index: {retriever.size} passage(s)\n")
    for score, passage in retriever.search(args.query, k=args.k):
        print(f"[{score:.3f}] {passage.clause}  ({passage.source})")
        print(f"    {passage.text[:200].strip()}...\n")
    return 0


def cmd_load_policy(args: argparse.Namespace) -> int:
    n = load_policy_into_supabase(args.policy_dir)
    print(f"\nLoaded {n} passage(s) into the Supabase vector store.\n")
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

    tune_p = sub.add_parser("tune", help="sweep routing thresholds against the gold set")
    tune_p.add_argument("--samples", default="data/samples")
    tune_p.add_argument("--labels", default="data/labels.jsonl")
    tune_p.set_defaults(func=cmd_tune)

    ft_p = sub.add_parser("export-ft", help="write a fine-tune dataset (no job launched)")
    ft_p.add_argument("--samples", default="data/samples")
    ft_p.add_argument("--labels", default="data/labels.jsonl")
    ft_p.add_argument("--out", default="data/finetune.jsonl")
    ft_p.set_defaults(func=cmd_export)

    ret_p = sub.add_parser("retrieve", help="inspect the policy index")
    ret_p.add_argument("query")
    ret_p.add_argument("-k", type=int, default=3)
    ret_p.set_defaults(func=cmd_retrieve)

    load_p = sub.add_parser("load-policy", help="embed the policy corpus into Supabase")
    load_p.add_argument("--policy-dir", default="data/policy")
    load_p.set_defaults(func=cmd_load_policy)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
