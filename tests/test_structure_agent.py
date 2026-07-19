from engine.agents import structure_agent
from engine.llm import LLMResult


def _fake_call_llm_json(messages, *, agent_name, schema, **kwargs):
    outline = schema(
        title="A Paper",
        sections=["abstract", "introduction"],
        section_plans={
            "abstract": {"key_points": ["state the contribution"], "target_word_count": 150},
            "introduction": {"key_points": ["motivate", "state RQs"], "target_word_count": 500},
        },
    )
    return outline, LLMResult(content="{}", model="fake/model", prompt_tokens=20, completion_tokens=10)


def test_structure_agent_produces_outline(monkeypatch):
    monkeypatch.setattr(structure_agent, "call_llm_json", _fake_call_llm_json)
    monkeypatch.setattr(structure_agent, "get_venue", lambda slug: None)

    from engine.state import PaperState

    state = PaperState(paper_id="demo", topic="x", venue=None)
    result = structure_agent.structure_agent(state)

    assert result.update["outline"]["sections"] == ["abstract", "introduction"]
    assert result.update["outline"]["section_plans"]["introduction"]["target_word_count"] == 500
