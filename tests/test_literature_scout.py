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
