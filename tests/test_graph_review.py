from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command

from engine.agents._shared import current_round_number
from engine.agents.base import NodeResult
from engine.graphs import review
from engine.graphs._registry import ERROR_GATE, error_gate
from engine.state import PaperState


def _stub_section_drafters(state):
    return {}  # pretend a redraft happened; loop back into review


def _build_review_test_graph():
    builder = StateGraph(PaperState)
    review.add_review_nodes(builder)
    builder.add_node(review.REVISION_LOOP_TARGET, _stub_section_drafters)
    builder.add_node(ERROR_GATE, error_gate)
    builder.add_edge(START, review.ENTRY_NODE)
    builder.add_edge(review.REVISION_LOOP_TARGET, review.ENTRY_NODE)
    builder.add_edge(review.REVIEW_COMPLETE, END)
    builder.add_edge(review.REVISION_MAX_LOOPS_GATE, END)
    builder.add_edge(ERROR_GATE, END)
    return builder


def _fake_no_op(update=None):
    def _fake(state):
        return NodeResult(update=update or {})

    return _fake


def test_converges_immediately_with_no_concerns(monkeypatch):
    monkeypatch.setattr(review, "adversarial_reviewer_ensemble", _fake_no_op())
    monkeypatch.setattr(review, "claims_evidence_auditor", _fake_no_op())
    monkeypatch.setattr(review, "flow_checker", _fake_no_op())
    monkeypatch.setattr(review, "compliance_checker", _fake_no_op())

    def real_revision_router(state):
        from engine.agents.revision_router import revision_router as impl

        return impl(state)

    monkeypatch.setattr(review, "revision_router", real_revision_router)

    with SqliteSaver.from_conn_string(":memory:") as cp:
        graph = _build_review_test_graph().compile(checkpointer=cp)
        config = {"configurable": {"thread_id": "demo"}}
        final = graph.invoke({"paper_id": "demo", "topic": "x", "phase": "review"}, config)

        assert "__interrupt__" not in final
        assert final["phase"] == "done"
        assert final["review_rounds"][-1].resolved is True


def test_loops_once_then_converges(monkeypatch):
    def reviewer_ensemble_by_round(state):
        round_num = current_round_number(state) if state.review_rounds else 1
        # First pass (no rounds recorded yet) raises a major concern; subsequent
        # passes (this node running again after the stub redraft) come back clean.
        major = ["missing baseline"] if not state.review_rounds else []
        return NodeResult(update={"review_rounds": [{"round": round_num if not state.review_rounds else round_num + 1, "major_concerns": major}]})

    monkeypatch.setattr(review, "adversarial_reviewer_ensemble", reviewer_ensemble_by_round)
    monkeypatch.setattr(review, "claims_evidence_auditor", _fake_no_op())
    monkeypatch.setattr(review, "flow_checker", _fake_no_op())
    monkeypatch.setattr(review, "compliance_checker", _fake_no_op())

    def fake_revision_router(state):
        current = state.review_rounds[-1] if state.review_rounds else None
        major = current.major_concerns if current else []
        if not major:
            resolved = current.model_copy(update={"resolved": True})
            return NodeResult(update={"review_rounds": [resolved], "phase": "done"})
        return NodeResult(update={"revision_loop_count": state.revision_loop_count + 1, "phase": "revision"})

    monkeypatch.setattr(review, "revision_router", fake_revision_router)

    with SqliteSaver.from_conn_string(":memory:") as cp:
        graph = _build_review_test_graph().compile(checkpointer=cp)
        config = {"configurable": {"thread_id": "demo"}}
        final = graph.invoke({"paper_id": "demo", "topic": "x", "phase": "review"}, config)

        assert final["phase"] == "done"
        # raw append-only log: round 1 (major concern), round 2 (clean), round 2 (resolved correction)
        assert len(final["review_rounds"]) == 3
        by_round = {}
        for r in final["review_rounds"]:
            by_round[r["round"] if isinstance(r, dict) else r.round] = r
        assert len(by_round) == 2  # dedupes to 2 distinct rounds, matching effective_review_rounds()
        assert final["revision_loop_count"] == 1


def test_hits_loop_cap_then_interrupts_and_force_done(monkeypatch):
    def always_major(state):
        round_num = len(state.review_rounds) + 1
        return NodeResult(update={"review_rounds": [{"round": round_num, "major_concerns": ["still broken"]}]})

    monkeypatch.setattr(review, "adversarial_reviewer_ensemble", always_major)
    monkeypatch.setattr(review, "claims_evidence_auditor", _fake_no_op())
    monkeypatch.setattr(review, "flow_checker", _fake_no_op())
    monkeypatch.setattr(review, "compliance_checker", _fake_no_op())

    def fake_revision_router(state):
        from engine.config import MAX_REVISION_LOOPS

        if state.revision_loop_count >= MAX_REVISION_LOOPS:
            return NodeResult(update={})
        return NodeResult(update={"revision_loop_count": state.revision_loop_count + 1, "phase": "revision"})

    monkeypatch.setattr(review, "revision_router", fake_revision_router)

    with SqliteSaver.from_conn_string(":memory:") as cp:
        graph = _build_review_test_graph().compile(checkpointer=cp)
        config = {"configurable": {"thread_id": "demo"}}
        result = graph.invoke({"paper_id": "demo", "topic": "x", "phase": "review"}, config)

        assert "__interrupt__" in result
        assert result["__interrupt__"][0].value["type"] == "revision_cap_reached"
        assert result["revision_loop_count"] == 3

        final = graph.invoke(Command(resume={"decision": "force_done"}), config)
        assert final["phase"] == "done"
