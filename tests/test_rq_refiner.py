from engine.agents import rq_refiner
from engine.llm import LLMResult
from engine.state import PaperState


def _fake_call_llm_json(messages, *, agent_name, schema, **kwargs):
    plan = schema(
        research_questions=[
            {"question": "Does RQ1 hold?", "hypothesis": "H1"},
            {"question": "Does RQ2 hold?", "hypothesis": "H2"},
        ]
    )
    return plan, LLMResult(content="{}", model="fake/model", prompt_tokens=40, completion_tokens=20)


def test_rq_refiner_writes_questions(tmp_path, monkeypatch):
    monkeypatch.setattr(rq_refiner, "call_llm_json", _fake_call_llm_json)
    monkeypatch.setattr(rq_refiner.fs_guard, "PAPERS_ROOT", tmp_path)
    (tmp_path / "demo").mkdir()

    state = PaperState(
        paper_id="demo",
        topic="LLM agents for supply chain exception handling",
        novelty_verdict={"verdict": "PROCEED", "rationale": "distinct angle"},
    )
    result = rq_refiner.rq_refiner(state)

    assert result.update["research_questions"] == ["Does RQ1 hold?", "Does RQ2 hold?"]
    md_path = tmp_path / "demo" / "ideation" / "research_questions.md"
    assert md_path.exists()
    assert "H1" in md_path.read_text()
