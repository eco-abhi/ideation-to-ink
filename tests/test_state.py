from engine.state import Claim, PaperState


def test_defaults():
    state = PaperState(paper_id="demo", topic="LLM agents for supply chain exception handling")
    assert state.phase == "ideation"
    assert state.claims == []
    assert state.errors == []
    assert state.errors_acknowledged_count == 0


def test_claims_reducer_semantics_via_model_copy():
    state = PaperState(paper_id="demo", topic="x")
    state2 = state.model_copy(update={"claims": [*state.claims, Claim(id="c1", text="claim text")]})
    assert len(state2.claims) == 1
    assert state.claims == []  # original untouched


def test_phase_rejects_invalid_value():
    import pytest
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        PaperState(paper_id="demo", topic="x", phase="not-a-real-phase")
