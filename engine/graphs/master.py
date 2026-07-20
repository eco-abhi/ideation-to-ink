"""Composes all four phase graphs onto one StateGraph and drives the CLI's
`run`/`check` commands.

Cross-phase topology follows the spec's true phase order (ideation ->
experiments -> writing -> review), which is why phases were *built* in a
different order (writing/citation-gate and review were the two explicitly
called-out pause points, prioritized during development) -- see
graphs/ideation.py's module docstring for why every phase registers onto one
shared graph instead of nested LangGraph subgraphs (the revision loop needs to
jump back into a node the writing phase owns).
"""

from __future__ import annotations

import json
from typing import Any

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command

from engine.agents.adversarial_reviewer_ensemble import adversarial_reviewer_ensemble
from engine.agents.citation_verifier import citation_verifier
from engine.agents.rebuttal_writer import rebuttal_writer
from engine.agents.redline_diff import redline_diff
from engine.agents.state_compaction import state_compaction
from engine.config import checkpoint_path, paper_dir
from engine.graphs import experiments, ideation, review, writing
from engine.graphs._registry import ERROR_GATE, error_gate
from engine.state import PaperState
from engine.tools.workspace import load_paper_yaml, save_paper_yaml

PHASE_ENTRY: dict[str, str] = {
    "ideation": ideation.ENTRY_NODE,
    "experiments": experiments.ENTRY_NODE,
    "writing": writing.ENTRY_NODE,
    "review": review.ENTRY_NODE,
    "revision": review.REVISION_LOOP_TARGET,  # "section_drafters" -- resume mid-loop, not a fresh outline
    "done": END,
}

# Agents runnable standalone via `engine check --agent <name>`, per the spec's
# "Standalone audits" CLI feature. Each maps a check-name to its function.
CHECK_AGENTS: dict[str, Any] = {
    "review_ensemble": adversarial_reviewer_ensemble,
    "citation_verifier": citation_verifier,
    "redline_diff": redline_diff,
    "rebuttal_writer": rebuttal_writer,
    "state_compaction": state_compaction,
}


def _route_entry(state: PaperState) -> str:
    return PHASE_ENTRY.get(state.phase, ideation.ENTRY_NODE)


def build_master_graph() -> StateGraph:
    builder = StateGraph(PaperState)

    ideation.add_ideation_nodes(builder)
    experiments.add_experiments_nodes(builder)
    writing.add_writing_nodes(builder)
    review.add_review_nodes(builder)

    builder.add_node(ERROR_GATE, error_gate)
    builder.add_edge(ERROR_GATE, END)

    # cross-phase edges, true spec order
    builder.add_edge(ideation.IDEATION_COMPLETE, experiments.ENTRY_NODE)
    builder.add_edge(experiments.EXPERIMENTS_COMPLETE, writing.ENTRY_NODE)
    builder.add_edge(writing.WRITING_COMPLETE, review.ENTRY_NODE)
    # review.py's revision_router already routes to "section_drafters" by name;
    # that node now exists because writing.add_writing_nodes ran on this same
    # builder, so the edge resolves with no further wiring needed here.

    builder.add_conditional_edges(START, _route_entry, {**{v: v for v in PHASE_ENTRY.values()}, END: END})

    return builder


def _interrupt_payload(result: dict[str, Any]) -> dict[str, Any] | None:
    interrupts = result.get("__interrupt__")
    if not interrupts:
        return None
    return interrupts[0].value


def _human_input_path(paper_id: str):
    return paper_dir(paper_id) / "HUMAN_INPUT_NEEDED.json"


def _human_response_path(paper_id: str):
    return paper_dir(paper_id) / "HUMAN_RESPONSE.json"


def run_paper(paper_id: str, *, target_phase: str | None = None, resume: bool = False) -> None:
    doc = load_paper_yaml(paper_id)
    if target_phase:
        doc["phase"] = target_phase
        save_paper_yaml(paper_id, doc)

    builder = build_master_graph()
    config = {"configurable": {"thread_id": paper_id}}

    with SqliteSaver.from_conn_string(str(checkpoint_path(paper_id))) as checkpointer:
        graph = builder.compile(checkpointer=checkpointer)
        snapshot = graph.get_state(config)
        has_pending_work = bool(snapshot.next)

        if has_pending_work:
            if not resume:
                print(
                    f"papers/{paper_id}/ has pending work (paused). Review "
                    f"HUMAN_INPUT_NEEDED.json and rerun with --resume."
                )
                return
            response_path = _human_response_path(paper_id)
            if not response_path.exists():
                raise SystemExit(
                    f"--resume requested but {response_path} doesn't exist. "
                    "Create it with your decision (see HUMAN_INPUT_NEEDED.json) and rerun."
                )
            response = json.loads(response_path.read_text())
            # Command(resume=None) and Command(resume={}) are both ambiguous/broken in
            # this LangGraph version (see tests/test_graph_ideation.py) -- HUMAN_RESPONSE.json
            # must always contain a concrete, non-empty value.
            result = graph.invoke(Command(resume=response), config)
            response_path.unlink()  # consumed -- delete now so a later re-pause doesn't leave it looking pending
        else:
            initial = {
                "paper_id": paper_id,
                "topic": doc["topic"],
                "phase": doc.get("phase", "ideation"),
                "venue": doc.get("venue"),
            }
            result = graph.invoke(initial, config)

        payload = _interrupt_payload(result)
        if payload is not None:
            _human_input_path(paper_id).write_text(json.dumps(payload, indent=2, default=str))
            print(f"Paused: {payload.get('type')}. See papers/{paper_id}/HUMAN_INPUT_NEEDED.json")
            return

        response_path = _human_response_path(paper_id)
        if response_path.exists():
            response_path.unlink()
        input_needed_path = _human_input_path(paper_id)
        if input_needed_path.exists():
            input_needed_path.unlink()

        doc = load_paper_yaml(paper_id)
        doc["phase"] = result.get("phase", doc.get("phase"))
        doc["status"] = "done" if doc["phase"] == "done" else "in_progress"
        save_paper_yaml(paper_id, doc)
        print(f"papers/{paper_id}/ now at phase={doc['phase']}")

        if doc["phase"] == "done":
            try:
                state_compaction(PaperState.model_validate(result))
            except Exception as exc:  # noqa: BLE001 -- best-effort wrap-up, never block a completed run on this
                print(f"(note: state ledger write failed: {exc})")


def run_single_agent(paper_id: str, *, agent_name: str) -> None:
    if agent_name not in CHECK_AGENTS:
        raise SystemExit(f"Unknown agent {agent_name!r}. Available: {sorted(CHECK_AGENTS)}")

    doc = load_paper_yaml(paper_id)
    state = PaperState(paper_id=paper_id, topic=doc["topic"], venue=doc.get("venue"), phase=doc.get("phase", "ideation"))

    builder = build_master_graph()
    with SqliteSaver.from_conn_string(str(checkpoint_path(paper_id))) as checkpointer:
        graph = builder.compile(checkpointer=checkpointer)
        snapshot = graph.get_state({"configurable": {"thread_id": paper_id}})
        if snapshot and snapshot.values:
            state = PaperState.model_validate(snapshot.values)

    result = CHECK_AGENTS[agent_name](state)
    print(f"{agent_name}: {result.output_summary}")
    if result.artifacts_written:
        print("Artifacts written:")
        for relpath in result.artifacts_written:
            print(f"  papers/{paper_id}/{relpath}")
