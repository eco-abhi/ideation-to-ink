import pytest
import yaml

from engine.agents import venue_strategist
from engine.llm import LLMResult
from engine.state import PaperState

FAKE_VENUES = [
    {"slug": "neurips-style", "name": "NeurIPS-style", "family": "ml-conference", "scope_keywords": ["ml"]},
    {"slug": "or-scm-journal", "name": "OR/SCM Journal", "family": "journal", "scope_keywords": ["scm"]},
]


def _fake_call_llm_json_factory(chosen_slug: str):
    def _fake(messages, *, agent_name, schema, **kwargs):
        strategy = schema(
            rankings=[
                {"slug": "neurips-style", "rank": 1, "rationale": "fits ML scope"},
                {"slug": "or-scm-journal", "rank": 2, "rationale": "fits SCM scope"},
            ],
            chosen_slug=chosen_slug,
            chosen_rationale="best overall fit",
        )
        return strategy, LLMResult(content="{}", model="fake/model", prompt_tokens=30, completion_tokens=15)

    return _fake


def test_venue_strategist_writes_choice_to_paper_yaml(tmp_path, monkeypatch):
    monkeypatch.setattr(venue_strategist, "list_venues", lambda: FAKE_VENUES)
    monkeypatch.setattr(venue_strategist, "call_llm_json", _fake_call_llm_json_factory("neurips-style"))
    monkeypatch.setattr(venue_strategist, "paper_dir", lambda slug: tmp_path / slug)
    monkeypatch.setattr(venue_strategist.fs_guard, "PAPERS_ROOT", tmp_path)

    pdir = tmp_path / "demo"
    pdir.mkdir()
    (pdir / "paper.yaml").write_text(yaml.safe_dump({"paper_id": "demo", "topic": "x", "phase": "ideation"}))

    state = PaperState(paper_id="demo", topic="x", research_questions=["q1"])
    result = venue_strategist.venue_strategist(state)

    assert result.update["venue"] == "neurips-style"
    doc = yaml.safe_load((pdir / "paper.yaml").read_text())
    assert doc["venue"] == "neurips-style"
    assert doc["venue_rationale"] == "best overall fit"
    assert len(doc["venue_rankings"]) == 2


def test_venue_strategist_rejects_hallucinated_slug(tmp_path, monkeypatch):
    monkeypatch.setattr(venue_strategist, "list_venues", lambda: FAKE_VENUES)
    monkeypatch.setattr(venue_strategist, "call_llm_json", _fake_call_llm_json_factory("made-up-venue"))
    monkeypatch.setattr(venue_strategist, "paper_dir", lambda slug: tmp_path / slug)
    monkeypatch.setattr(venue_strategist.fs_guard, "PAPERS_ROOT", tmp_path)

    pdir = tmp_path / "demo"
    pdir.mkdir()
    (pdir / "paper.yaml").write_text(yaml.safe_dump({"paper_id": "demo"}))

    state = PaperState(paper_id="demo", topic="x")
    with pytest.raises(ValueError, match="not one of the configured venues"):
        venue_strategist.venue_strategist(state)
