from engine.agents import revision_router
from engine.config import MAX_REVISION_LOOPS
from engine.llm import LLMResult
from engine.state import PaperState, ReviewRound


def test_converged_sets_phase_done(tmp_path):
    state = PaperState(
        paper_id="demo",
        topic="x",
        review_rounds=[ReviewRound(round=1, major_concerns=[])],
    )
    result = revision_router.revision_router(state)
    assert result.update["phase"] == "done"
    assert result.update["review_rounds"][0].resolved is True


def test_loops_back_with_revision_brief(tmp_path, monkeypatch):
    def fake_call_llm_json(messages, *, agent_name, schema, **kwargs):
        brief = schema(section_instructions={"methods": "Add an ablation study."})
        return brief, LLMResult(content="{}", model="fake/model", prompt_tokens=5, completion_tokens=5)

    monkeypatch.setattr(revision_router, "call_llm_json", fake_call_llm_json)
    monkeypatch.setattr(revision_router.fs_guard, "PAPERS_ROOT", tmp_path)
    (tmp_path / "demo").mkdir()

    state = PaperState(
        paper_id="demo",
        topic="x",
        outline={"sections": ["methods"]},
        review_rounds=[ReviewRound(round=1, major_concerns=["missing ablation"])],
        revision_loop_count=0,
    )
    result = revision_router.revision_router(state)

    assert result.update["phase"] == "revision"
    assert result.update["revision_loop_count"] == 1
    brief_path = tmp_path / "demo" / "reviews" / "round_01" / "revision_brief.md"
    assert brief_path.exists()
    assert "Add an ablation study." in brief_path.read_text()


def test_cap_reached_leaves_state_for_max_loops_gate():
    state = PaperState(
        paper_id="demo",
        topic="x",
        review_rounds=[ReviewRound(round=4, major_concerns=["still broken"])],
        revision_loop_count=MAX_REVISION_LOOPS,
    )
    result = revision_router.revision_router(state)
    assert result.update == {}
