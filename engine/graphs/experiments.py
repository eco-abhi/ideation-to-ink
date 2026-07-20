"""Phase 2 (Experiments): methodology_designer -> [human approval gate] ->
experiment_scaffolder -> [results-ready gate] -> stats_validator -> experiments_complete.

Execution of the scaffolded experiments is explicitly out of scope for this graph
(human/Claude-Code-driven, per the repo's guardrails) -- results_gate is what
pauses the pipeline until experiments/results/metrics.json exists.
"""

from __future__ import annotations

from typing import Any

from langgraph.graph import END
from langgraph.types import interrupt

from engine.agents.experiment_scaffolder import AGENT_NAME as SCAFFOLDER_NAME
from engine.agents.experiment_scaffolder import SKILL as SCAFFOLDER_SKILL
from engine.agents.experiment_scaffolder import experiment_scaffolder
from engine.agents.methodology_designer import AGENT_NAME as METHODOLOGY_DESIGNER_NAME
from engine.agents.methodology_designer import SKILL as METHODOLOGY_DESIGNER_SKILL
from engine.agents.methodology_designer import methodology_designer
from engine.agents.stats_validator import AGENT_NAME as STATS_VALIDATOR_NAME
from engine.agents.stats_validator import RESULTS_RELPATH, stats_validator
from engine.agents.stats_validator import SKILL as STATS_VALIDATOR_SKILL
from engine.config import paper_dir
from engine.graphs._registry import ERROR_GATE, route_after, traced_node
from engine.state import PaperState

METHODOLOGY_HUMAN_GATE = "methodology_human_gate"
RESULTS_GATE = "results_gate"
EXPERIMENTS_COMPLETE = "experiments_complete"
ENTRY_NODE = "methodology_designer"


def methodology_human_gate(state: PaperState) -> dict[str, Any]:
    decision = interrupt(
        {
            "type": "methodology_approval",
            "paper_id": state.paper_id,
            "design_path": state.artifacts.get("design"),
            "instructions": (
                "Review experiments/DESIGN.md. Resume with {'decision': 'approve'} to scaffold "
                "experiments, or {'decision': 'revise'} to stop here and edit DESIGN.md by hand."
            ),
        }
    )
    chosen = (decision or {}).get("decision", "approve") if isinstance(decision, dict) else "approve"
    return {"artifacts": {**state.artifacts, "methodology_decision": chosen}}


def _route_after_methodology_gate(state: PaperState) -> str:
    return "experiment_scaffolder" if state.artifacts.get("methodology_decision") == "approve" else END


def results_gate(state: PaperState) -> dict[str, Any]:
    results_path = paper_dir(state.paper_id) / RESULTS_RELPATH
    if results_path.exists():
        return {}
    interrupt(
        {
            "type": "awaiting_experiment_results",
            "paper_id": state.paper_id,
            "instructions": (
                f"Run the scaffolded experiments (experiments/src/run_experiment.py) and write "
                f"results to {RESULTS_RELPATH}, then resume."
            ),
        }
    )
    return {}


def _mark_experiments_complete(state: PaperState) -> dict[str, Any]:
    return {}


def add_experiments_nodes(builder: Any) -> None:
    builder.add_node(
        "methodology_designer",
        traced_node(METHODOLOGY_DESIGNER_NAME, methodology_designer, skill=METHODOLOGY_DESIGNER_SKILL),
    )
    builder.add_node(METHODOLOGY_HUMAN_GATE, methodology_human_gate)
    builder.add_node(
        "experiment_scaffolder", traced_node(SCAFFOLDER_NAME, experiment_scaffolder, skill=SCAFFOLDER_SKILL)
    )
    builder.add_node(RESULTS_GATE, results_gate)
    builder.add_node("stats_validator", traced_node(STATS_VALIDATOR_NAME, stats_validator, skill=STATS_VALIDATOR_SKILL))
    builder.add_node(EXPERIMENTS_COMPLETE, _mark_experiments_complete)

    builder.add_conditional_edges(
        "methodology_designer",
        route_after(METHODOLOGY_HUMAN_GATE),
        {METHODOLOGY_HUMAN_GATE: METHODOLOGY_HUMAN_GATE, ERROR_GATE: ERROR_GATE},
    )
    builder.add_conditional_edges(
        METHODOLOGY_HUMAN_GATE,
        _route_after_methodology_gate,
        {"experiment_scaffolder": "experiment_scaffolder", END: END},
    )
    builder.add_conditional_edges(
        "experiment_scaffolder",
        route_after(RESULTS_GATE),
        {RESULTS_GATE: RESULTS_GATE, ERROR_GATE: ERROR_GATE},
    )
    builder.add_edge(RESULTS_GATE, "stats_validator")
    builder.add_conditional_edges(
        "stats_validator",
        route_after(EXPERIMENTS_COMPLETE),
        {EXPERIMENTS_COMPLETE: EXPERIMENTS_COMPLETE, ERROR_GATE: ERROR_GATE},
    )
