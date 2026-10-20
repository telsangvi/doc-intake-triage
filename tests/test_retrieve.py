"""The policy index and the citation path."""
from pathlib import Path

import pytest

from src.llm import MockLLM
from src.pipeline import process_directory
from src.retrieve import Retriever, build_index, build_retriever, chunk_markdown, default_retriever

DATA = Path(__file__).resolve().parent.parent / "data"


def test_chunking_keeps_clause_ids():
    text = "# Policy 9.9\n\n## 9.9(a) First\nSome rule text.\n\n## 9.9(b) Second\nMore."
    passages = chunk_markdown(text, "x.md")
    assert [p.clause for p in passages] == ["9.9(a) First", "9.9(b) Second"]


def test_income_query_finds_the_income_clause():
    retriever = default_retriever()
    hits = retriever.search("monthly household income salary slip evidence", k=3)
    assert hits, "expected at least one policy passage"
    assert any("Income" in p.clause or "4.2" in p.clause for _, p in hits)


def test_index_loads_the_bundled_corpus():
    retriever = build_index(DATA / "policy")
    assert retriever.size >= 4


def test_routing_attaches_a_policy_reference():
    results = {r.source_file: r for r in process_directory(DATA / "samples", MockLLM())}
    incomplete = results["case_002_application.txt"]
    assert incomplete.decision.value == "incomplete"
    assert incomplete.policy_refs, "an incomplete case should cite a policy clause"


def test_backend_defaults_to_offline_memory():
    assert isinstance(build_retriever("memory"), Retriever)


def test_unknown_backend_is_rejected():
    with pytest.raises(ValueError):
        build_retriever("nonsense")


def test_embedding_dimension_matches_the_schema():
    """The offline embedder must produce vectors the DB column can accept."""
    from src.config import settings

    vec = build_index(DATA / "policy").embedder.embed(["test"])[0]
    assert len(vec) == settings.embedding_dim
