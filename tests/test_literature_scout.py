import pandas as pd

from engine.agents import literature_scout
from engine.llm import LLMResult
from engine.state import PaperState
from engine.tools.common import SearchResult


def _fake_call_llm_json(messages, *, agent_name, schema, **kwargs):
    expansion = schema(queries=["agentic exception handling", "supply chain LLM agents"])
    result = LLMResult(content="{}", model="fake/model", prompt_tokens=50, completion_tokens=10)
    return expansion, result


def _result(title: str, doi: str | None = None, source: str = "openalex") -> SearchResult:
    return SearchResult(title=title, doi=doi, year=2024, source=source)


def test_literature_scout_dedupes_and_writes_corpus(tmp_path, monkeypatch):
    monkeypatch.setattr(literature_scout, "call_llm_json", _fake_call_llm_json)

    # Same DOI from two sources -> dedup by DOI. Near-identical title -> dedup by title.
    monkeypatch.setattr(
        literature_scout.openalex,
        "search",
        lambda q, limit: [_result("Agentic Supply Chains", doi="10.1/x"), _result("Predicting Retail Demand with Transformers")],
    )
    monkeypatch.setattr(
        literature_scout.semanticscholar,
        "search",
        lambda q, limit: [
            _result("Agentic Supply Chains", doi="10.1/x", source="semanticscholar"),
            _result("Agentic Supply Chain", source="semanticscholar"),  # near-duplicate title, no DOI
        ],
    )
    monkeypatch.setattr(literature_scout.arxiv, "search", lambda q, limit: [_result("Vehicle Routing under Uncertainty", source="arxiv")])

    monkeypatch.setattr(literature_scout.fs_guard, "PAPERS_ROOT", tmp_path)
    (tmp_path / "demo").mkdir()

    state = PaperState(paper_id="demo", topic="LLM agents for supply chain exception handling")
    result = literature_scout.literature_scout(state)

    # 2 queries expanded to 3 total (topic + 2) x 3 sources, but mocks ignore query text
    assert result.model == "fake/model"
    assert result.prompt_tokens == 50
    assert "corpus" in result.update["artifacts"]

    corpus_path = tmp_path / "demo" / "ideation" / "corpus.parquet"
    assert corpus_path.exists()
    df = pd.read_parquet(corpus_path)
    titles = set(df["title"])
    assert "Predicting Retail Demand with Transformers" in titles
    assert "Vehicle Routing under Uncertainty" in titles
    # only one of the two near-duplicate "Agentic Supply Chain(s)" titles should survive
    assert sum(1 for t in titles if t.startswith("Agentic Supply Chain")) == 1


def test_long_abstract_never_becomes_a_literal_search_query(tmp_path, monkeypatch):
    # Regression test: a pasted full-paper abstract as `topic` was sent verbatim
    # to OpenAlex as a literal `search=` query and got a 400 Bad Request (query
    # string several thousand characters long). topic is now contractually a
    # short title; abstract/keywords are LLM context only, never a literal query.
    monkeypatch.setattr(literature_scout, "call_llm_json", _fake_call_llm_json)

    queries_seen: list[str] = []

    def _record_and_search(q, limit):
        queries_seen.append(q)
        return []

    monkeypatch.setattr(literature_scout.openalex, "search", _record_and_search)
    monkeypatch.setattr(literature_scout.semanticscholar, "search", _record_and_search)
    monkeypatch.setattr(literature_scout.arxiv, "search", _record_and_search)
    monkeypatch.setattr(literature_scout.fs_guard, "PAPERS_ROOT", tmp_path)
    (tmp_path / "demo").mkdir()

    long_abstract = "This paper proposes a framework. " * 300  # several thousand chars
    state = PaperState(
        paper_id="demo",
        topic="Criticality-Conditioned Schedule Compliance Prediction",
        keywords=["ABC classification", "compliance prediction"],
        abstract=long_abstract,
    )
    literature_scout.literature_scout(state)

    assert queries_seen  # sanity: searches actually ran
    for q in queries_seen:
        assert q == state.topic or q in {"agentic exception handling", "supply chain LLM agents"}
        assert long_abstract not in q
        assert len(q) < 200
