from graph_helpers import compiled_graph
from langgraph.types import Command

from engine.agents.base import NodeResult
from engine.graphs import experiments


def _fake_methodology_designer(state):
    return NodeResult(update={"artifacts": {**state.artifacts, "design": "experiments/DESIGN.md"}})


def _fake_experiment_scaffolder(state):
    return NodeResult(update={"artifacts": {**state.artifacts, "experiment_runner": "experiments/src/run_experiment.py"}})


def _fake_stats_validator(state):
    return NodeResult(update={"artifacts": {**state.artifacts, "results_report": "experiments/results_report.md"}})


def test_approval_and_results_ready_reaches_completion(tmp_path, monkeypatch):
    monkeypatch.setattr(experiments, "methodology_designer", _fake_methodology_designer)
    monkeypatch.setattr(experiments, "experiment_scaffolder", _fake_experiment_scaffolder)
    monkeypatch.setattr(experiments, "stats_validator", _fake_stats_validator)
    monkeypatch.setattr(experiments, "paper_dir", lambda slug: tmp_path / slug)

    results_dir = tmp_path / "demo" / "experiments" / "results"
    results_dir.mkdir(parents=True)
    (results_dir / "metrics.json").write_text("{}")

    with compiled_graph(
        experiments.add_experiments_nodes, entry_node=experiments.ENTRY_NODE, exit_node=experiments.EXPERIMENTS_COMPLETE
    ) as graph:
        config = {"configurable": {"thread_id": "demo"}}
        result = graph.invoke({"paper_id": "demo", "topic": "x", "phase": "experiments"}, config)
        assert "__interrupt__" in result
        assert result["__interrupt__"][0].value["type"] == "methodology_approval"

        # results already present -> results_gate passes straight through without a second interrupt
        final = graph.invoke(Command(resume={"decision": "approve"}), config)
        assert "__interrupt__" not in final
        assert final["artifacts"]["results_report"] == "experiments/results_report.md"


def test_methodology_revision_declined_ends_run(monkeypatch):
    monkeypatch.setattr(experiments, "methodology_designer", _fake_methodology_designer)

    def _fail_if_called(state):
        raise AssertionError("should not scaffold after a 'revise' decision")

    monkeypatch.setattr(experiments, "experiment_scaffolder", _fail_if_called)

    with compiled_graph(
        experiments.add_experiments_nodes, entry_node=experiments.ENTRY_NODE, exit_node=experiments.EXPERIMENTS_COMPLETE
    ) as graph:
        config = {"configurable": {"thread_id": "demo-revise"}}
        graph.invoke({"paper_id": "demo-revise", "topic": "x", "phase": "experiments"}, config)
        final = graph.invoke(Command(resume={"decision": "revise"}), config)
        assert final["artifacts"].get("experiment_runner") is None


def test_results_gate_waits_for_metrics_file(tmp_path, monkeypatch):
    monkeypatch.setattr(experiments, "methodology_designer", _fake_methodology_designer)
    monkeypatch.setattr(experiments, "experiment_scaffolder", _fake_experiment_scaffolder)
    monkeypatch.setattr(experiments, "stats_validator", _fake_stats_validator)
    monkeypatch.setattr(experiments, "paper_dir", lambda slug: tmp_path / slug)
    (tmp_path / "demo").mkdir()  # no experiments/results/metrics.json yet

    with compiled_graph(
        experiments.add_experiments_nodes, entry_node=experiments.ENTRY_NODE, exit_node=experiments.EXPERIMENTS_COMPLETE
    ) as graph:
        config = {"configurable": {"thread_id": "demo-wait"}}
        graph.invoke({"paper_id": "demo", "topic": "x", "phase": "experiments"}, config)
        result = graph.invoke(Command(resume={"decision": "approve"}), config)

        assert "__interrupt__" in result
        assert result["__interrupt__"][0].value["type"] == "awaiting_experiment_results"

        # simulate the human running the scaffolded experiments now
        (tmp_path / "demo" / "experiments" / "results").mkdir(parents=True)
        (tmp_path / "demo" / "experiments" / "results" / "metrics.json").write_text("{}")

        final = graph.invoke(Command(resume="ack"), config)
        assert "__interrupt__" not in final
        assert final["artifacts"]["results_report"] == "experiments/results_report.md"
