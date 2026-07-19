import pandas as pd
import pytest

from engine.agents import novelty_checker
from engine.llm import LLMResult
from engine.state import PaperState


def _fake_embed_texts(texts, **kwargs):
    # claim vector + one vector per abstract; make the first corpus item near-identical
    # to the claim (high similarity) and the rest orthogonal.
    n = len(texts) - 1
    vectors = [[1.0, 0.0, 0.0]]  # claim
    vectors.append([0.99, 0.01, 0.0])  # near-duplicate work
    for i in range(n - 1):
        vectors.append([0.0, 1.0, float(i)])
    return vectors


def _fake_call_llm_json_stop(messages, *, agent_name, schema, **kwargs):
    verdict = schema(verdict="STOP", rationale="Nearest work already answers this question.")
    return verdict, LLMResult(content="{}", model="fake/model", prompt_tokens=80, completion_tokens=15)


def _make_corpus(tmp_path, n=6):
    df = pd.DataFrame(
        [
            {
                "title": f"Existing Work {i}",
                "abstract": f"Abstract text for work {i} about related methods.",
                "year": 2020 + i,
                "venue": "X",
                "doi": None,
                "arxiv_id": None,
                "citation_count": i,
                "authors": ["A"],
                "source": "openalex",
            }
            for i in range(n)
        ]
    )
    path = tmp_path / "corpus.parquet"
    df.to_parquet(path)
    return str(path)


def test_novelty_checker_stop_verdict(tmp_path, monkeypatch):
    monkeypatch.setattr(novelty_checker, "embed_texts", _fake_embed_texts)
    monkeypatch.setattr(novelty_checker, "call_llm_json", _fake_call_llm_json_stop)
    monkeypatch.setattr(novelty_checker.fs_guard, "PAPERS_ROOT", tmp_path)
    (tmp_path / "demo").mkdir()

    corpus_path = _make_corpus(tmp_path)
    state = PaperState(paper_id="demo", topic="A topic very close to Existing Work 0", corpus_path=corpus_path)

    result = novelty_checker.novelty_checker(state)

    assert result.update["novelty_verdict"]["verdict"] == "STOP"
    assert result.update["novelty_verdict"]["score"] > 0.9
    report_path = tmp_path / "demo" / "ideation" / "novelty_report.md"
    assert report_path.exists()
    assert "STOP" in report_path.read_text()


def test_novelty_checker_requires_corpus():
    state = PaperState(paper_id="demo", topic="x", corpus_path=None)
    with pytest.raises(ValueError, match="corpus_path"):
        novelty_checker.novelty_checker(state)
