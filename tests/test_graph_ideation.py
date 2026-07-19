from graph_helpers import compiled_graph
from langgraph.types import Command

from engine.agents.base import NodeResult
from engine.graphs import ideation


def _fake_literature_scout(state):
    return NodeResult(update={"corpus_path": "/fake/corpus.parquet"}, output_summary="fake corpus")


def _fake_literature_scout_fails(state):
    raise RuntimeError("network down")


def _make_fake_novelty_checker(verdict: str, score: float = 0.5):
    def _fake(state):
        return NodeResult(update={"novelty_verdict": {"verdict": verdict, "score": score, "rationale": "r"}})

    return _fake


def _fake_rq_refiner(state):
    return NodeResult(update={"research_questions": ["q1", "q2"]})


def _fake_venue_strategist(state):
    return NodeResult(update={"venue": "neurips-style"})


def test_happy_path_proceeds_through_interrupt_to_completion(monkeypatch):
    monkeypatch.setattr(ideation, "literature_scout", _fake_literature_scout)
    monkeypatch.setattr(ideation, "novelty_checker", _make_fake_novelty_checker("PROCEED"))
    monkeypatch.setattr(ideation, "rq_refiner", _fake_rq_refiner)
    monkeypatch.setattr(ideation, "venue_strategist", _fake_venue_strategist)

    with compiled_graph(
        ideation.add_ideation_nodes, entry_node=ideation.ENTRY_NODE, exit_node=ideation.IDEATION_COMPLETE
    ) as graph:
        config = {"configurable": {"thread_id": "demo"}}
        initial = {"paper_id": "demo", "topic": "x", "phase": "ideation"}

        result = graph.invoke(initial, config)
        assert "__interrupt__" in result
        assert result["__interrupt__"][0].value["type"] == "novelty_verdict"

        final = graph.invoke(Command(resume={"decision": "proceed"}), config)
        assert "__interrupt__" not in final
        assert final["venue"] == "neurips-style"
        assert final["research_questions"] == ["q1", "q2"]
        assert final["errors"] == []


def test_stop_verdict_ends_without_downstream_nodes(monkeypatch):
    monkeypatch.setattr(ideation, "literature_scout", _fake_literature_scout)
    monkeypatch.setattr(ideation, "novelty_checker", _make_fake_novelty_checker("STOP", score=0.98))

    def _fail_if_called(state):
        raise AssertionError("should not be reached after STOP")

    monkeypatch.setattr(ideation, "rq_refiner", _fail_if_called)
    monkeypatch.setattr(ideation, "venue_strategist", _fail_if_called)

    with compiled_graph(
        ideation.add_ideation_nodes, entry_node=ideation.ENTRY_NODE, exit_node=ideation.IDEATION_COMPLETE
    ) as graph:
        config = {"configurable": {"thread_id": "demo-stop"}}
        initial = {"paper_id": "demo-stop", "topic": "x", "phase": "ideation"}

        graph.invoke(initial, config)
        # resume with no "decision" key -> default decision follows the STOP verdict
        # (an empty dict is ambiguous with LangGraph's multi-interrupt resume-map syntax)
        final = graph.invoke(Command(resume={"note": "no override"}), config)

        assert final.get("venue") is None
        assert final["novelty_verdict"]["human_decision"] == "stop"


def test_node_failure_routes_to_error_gate_and_records_error(monkeypatch):
    monkeypatch.setattr(ideation, "literature_scout", _fake_literature_scout_fails)

    with compiled_graph(
        ideation.add_ideation_nodes, entry_node=ideation.ENTRY_NODE, exit_node=ideation.IDEATION_COMPLETE
    ) as graph:
        config = {"configurable": {"thread_id": "demo-fail"}}
        initial = {"paper_id": "demo-fail", "topic": "x", "phase": "ideation"}

        result = graph.invoke(initial, config)
        assert "__interrupt__" in result
        assert result["__interrupt__"][0].value["type"] == "node_error"
        assert len(result["errors"]) == 1
        assert "network down" in result["errors"][0]

        # NOTE: neither `invoke(None, config)` nor `Command(resume=None)` actually
        # injects a resume value in this LangGraph version -- the former just replays
        # and re-fires the interrupt, the latter hits an internal UnboundLocalError.
        # A concrete scalar resume value is required even when error_gate ignores it.
        final = graph.invoke(Command(resume="acknowledged"), config)
        assert final["errors_acknowledged_count"] == 1


def test_kill_and_resume_across_checkpointer_reconnect(tmp_path, monkeypatch):
    monkeypatch.setattr(ideation, "literature_scout", _fake_literature_scout)
    monkeypatch.setattr(ideation, "novelty_checker", _make_fake_novelty_checker("PROCEED"))
    monkeypatch.setattr(ideation, "rq_refiner", _fake_rq_refiner)
    monkeypatch.setattr(ideation, "venue_strategist", _fake_venue_strategist)

    db_path = str(tmp_path / "resume-test.sqlite")
    config = {"configurable": {"thread_id": "demo-resume"}}
    initial = {"paper_id": "demo-resume", "topic": "x", "phase": "ideation"}

    with compiled_graph(
        ideation.add_ideation_nodes,
        entry_node=ideation.ENTRY_NODE,
        exit_node=ideation.IDEATION_COMPLETE,
        db_path=db_path,
    ) as graph:
        result = graph.invoke(initial, config)
        assert "__interrupt__" in result
    # simulate the process dying here -- graph object and connection are gone.

    with compiled_graph(
        ideation.add_ideation_nodes,
        entry_node=ideation.ENTRY_NODE,
        exit_node=ideation.IDEATION_COMPLETE,
        db_path=db_path,
    ) as graph:
        final = graph.invoke(Command(resume={"decision": "proceed"}), config)
        assert final["venue"] == "neurips-style"
        assert final["corpus_path"] == "/fake/corpus.parquet"
