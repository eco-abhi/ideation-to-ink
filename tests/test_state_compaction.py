from engine.agents import state_compaction
from engine.llm import LLMResult
from engine.state import CitationRecord, Claim, PaperState, ReviewRound


def _fake_call_llm_json(messages, *, agent_name, schema, **kwargs):
    ledger = schema(
        round_summaries=[{"round": 1, "summary": "Fixed missing baseline; converged."}],
        overall_summary="Paper progressed cleanly through one revision round.",
    )
    return ledger, LLMResult(content="{}", model="fake/model", prompt_tokens=10, completion_tokens=10)


def test_state_compaction_writes_ledger(tmp_path, monkeypatch):
    monkeypatch.setattr(state_compaction, "call_llm_json", _fake_call_llm_json)
    monkeypatch.setattr(state_compaction.fs_guard, "PAPERS_ROOT", tmp_path)
    (tmp_path / "demo").mkdir()

    state = PaperState(
        paper_id="demo",
        topic="x",
        venue="neurips-style",
        novelty_verdict={"verdict": "PROCEED"},
        claims=[Claim(id="c1", text="claim", status="supported")],
        citation_records=[CitationRecord(bib_key="k1", status="verified", rationale="ok")],
        review_rounds=[ReviewRound(round=1, major_concerns=[], resolved=True)],
    )
    result = state_compaction.state_compaction(state)

    ledger_path = tmp_path / "demo" / "provenance" / "state_ledger.md"
    assert ledger_path.exists()
    text = ledger_path.read_text()
    assert "Fixed missing baseline" in text
    assert "1/1 supported" in text
    assert "1/1 verified" in text
    assert result.update["artifacts"]["state_ledger"] == "provenance/state_ledger.md"


def test_should_compact_threshold():
    small_state = PaperState(paper_id="demo", topic="x")
    assert state_compaction.should_compact(small_state, threshold_bytes=10)
    assert not state_compaction.should_compact(small_state, threshold_bytes=1_000_000)
