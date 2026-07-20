import pytest

from engine.agents import rebuttal_writer, redline_diff
from engine.llm import LLMResult
from engine.state import PaperState, ReviewRound


def test_redline_diff_reports_no_changes_when_git_show_fails(tmp_path, monkeypatch):
    monkeypatch.setattr(redline_diff, "paper_dir", lambda slug: tmp_path / slug)
    monkeypatch.setattr(redline_diff.fs_guard, "PAPERS_ROOT", tmp_path)
    monkeypatch.setattr(redline_diff, "_git_show_head", lambda paper_id, relpath: None)

    pdir = tmp_path / "demo"
    (pdir / "manuscript" / "sections").mkdir(parents=True)
    (pdir / "manuscript" / "sections" / "intro.tex").write_text("New content.")

    state = PaperState(paper_id="demo", topic="x")
    result = redline_diff.redline_diff(state)

    report = (pdir / "manuscript" / "redline_diff.md").read_text()
    assert "intro" in report
    assert "New content" in report
    assert "1 section" in result.output_summary


def test_redline_diff_requires_sections_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(redline_diff, "paper_dir", lambda slug: tmp_path / slug)
    (tmp_path / "demo").mkdir()
    state = PaperState(paper_id="demo", topic="x")
    with pytest.raises(ValueError, match="manuscript/sections"):
        redline_diff.redline_diff(state)


def test_git_show_head_returns_none_on_failure(tmp_path):
    # real subprocess call against a path that doesn't exist in git -- should not raise
    result = redline_diff._git_show_head("nonexistent-paper", "manuscript/sections/x.tex")
    assert result is None


def test_rebuttal_writer_writes_response(tmp_path, monkeypatch):
    def fake_call_llm_json(messages, *, agent_name, schema, **kwargs):
        rebuttal = schema(
            summary="We address both concerns below.",
            points=[{"concern": "missing baseline", "response": "Added in Table 2."}],
        )
        return rebuttal, LLMResult(content="{}", model="fake/model", prompt_tokens=10, completion_tokens=10)

    monkeypatch.setattr(rebuttal_writer, "call_llm_json", fake_call_llm_json)
    monkeypatch.setattr(rebuttal_writer.fs_guard, "PAPERS_ROOT", tmp_path)
    (tmp_path / "demo").mkdir()

    state = PaperState(
        paper_id="demo", topic="x", review_rounds=[ReviewRound(round=2, major_concerns=["missing baseline"])]
    )
    result = rebuttal_writer.rebuttal_writer(state)

    rebuttal_path = tmp_path / "demo" / "reviews" / "round_02" / "rebuttal.md"
    assert rebuttal_path.exists()
    assert "Added in Table 2." in rebuttal_path.read_text()
    assert "round 2" in result.output_summary


def test_rebuttal_writer_requires_concerns():
    state = PaperState(paper_id="demo", topic="x", review_rounds=[ReviewRound(round=1, major_concerns=[])])
    with pytest.raises(ValueError, match="no concerns"):
        rebuttal_writer.rebuttal_writer(state)
