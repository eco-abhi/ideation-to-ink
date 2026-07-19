"""Phase 4 (Review): adversarial_reviewer_ensemble -> claims_evidence_auditor ->
flow_checker -> compliance_checker -> revision_router -> [loop back into
section_drafters | human gate at the loop cap | review_complete].

The loop-back target ("section_drafters") lives in graphs/writing.py, not here --
this is exactly the cross-phase jump the module-level docstring in
graphs/ideation.py explains: LangGraph subgraphs can't reach into another
subgraph's internal nodes, so every phase module registers onto one shared
StateGraph and graphs/master.py wires the cross-phase edges. Standalone tests of
this phase (tests/test_graph_review.py) register a stub "section_drafters" node
themselves to exercise the loop-back edge in isolation.
"""

from __future__ import annotations

from typing import Any

from langgraph.types import interrupt

from engine.agents._shared import current_round_number, get_current_round
from engine.agents.adversarial_reviewer_ensemble import AGENT_NAME as REVIEWER_ENSEMBLE_NAME
from engine.agents.adversarial_reviewer_ensemble import SKILL as REVIEWER_ENSEMBLE_SKILL
from engine.agents.adversarial_reviewer_ensemble import adversarial_reviewer_ensemble
from engine.agents.claims_evidence_auditor import AGENT_NAME as CLAIMS_AUDITOR_NAME
from engine.agents.claims_evidence_auditor import SKILL as CLAIMS_AUDITOR_SKILL
from engine.agents.claims_evidence_auditor import claims_evidence_auditor
from engine.agents.compliance_checker import AGENT_NAME as COMPLIANCE_CHECKER_NAME
from engine.agents.compliance_checker import SKILL as COMPLIANCE_CHECKER_SKILL
from engine.agents.compliance_checker import compliance_checker
from engine.agents.flow_checker import AGENT_NAME as FLOW_CHECKER_NAME
from engine.agents.flow_checker import SKILL as FLOW_CHECKER_SKILL
from engine.agents.flow_checker import flow_checker
from engine.agents.revision_router import AGENT_NAME as REVISION_ROUTER_NAME
from engine.agents.revision_router import SKILL as REVISION_ROUTER_SKILL
from engine.agents.revision_router import revision_router
from engine.config import MAX_REVISION_LOOPS
from engine.graphs._registry import ERROR_GATE, has_unacknowledged_errors, route_after, traced_node
from engine.state import PaperState

REVISION_MAX_LOOPS_GATE = "revision_max_loops_gate"
REVIEW_COMPLETE = "review_complete"
REVISION_LOOP_TARGET = "section_drafters"  # owned by graphs/writing.py; master.py resolves it
ENTRY_NODE = "adversarial_reviewer_ensemble"


def revision_max_loops_gate(state: PaperState) -> dict[str, Any]:
    current = get_current_round(state)
    decision = interrupt(
        {
            "type": "revision_cap_reached",
            "paper_id": state.paper_id,
            "loops_used": state.revision_loop_count,
            "remaining_major_concerns": current.major_concerns if current else [],
            "instructions": (
                "Resume with {'decision': 'force_done'} to accept the manuscript as-is despite "
                "unresolved concerns, or {'decision': 'abandon'} to stop here for manual intervention."
            ),
        }
    )
    chosen = (decision or {}).get("decision", "abandon") if isinstance(decision, dict) else "abandon"
    if chosen == "force_done":
        round_num = current_round_number(state)
        resolved = current.model_copy(update={"resolved": True}) if current else None
        update: dict[str, Any] = {"phase": "done"}
        if resolved:
            update["review_rounds"] = [resolved]
        else:
            from engine.state import ReviewRound

            update["review_rounds"] = [ReviewRound(round=round_num, resolved=True)]
        return update
    return {}


def _route_after_revision_router(state: PaperState) -> str:
    if has_unacknowledged_errors(state):
        return ERROR_GATE
    if state.phase == "done":
        return REVIEW_COMPLETE
    if state.revision_loop_count >= MAX_REVISION_LOOPS:
        return REVISION_MAX_LOOPS_GATE
    return REVISION_LOOP_TARGET


def _mark_review_complete(state: PaperState) -> dict[str, Any]:
    return {}


def add_review_nodes(builder: Any) -> None:
    builder.add_node(
        "adversarial_reviewer_ensemble",
        traced_node(REVIEWER_ENSEMBLE_NAME, adversarial_reviewer_ensemble, skill=REVIEWER_ENSEMBLE_SKILL),
    )
    builder.add_node(
        "claims_evidence_auditor", traced_node(CLAIMS_AUDITOR_NAME, claims_evidence_auditor, skill=CLAIMS_AUDITOR_SKILL)
    )
    builder.add_node("flow_checker", traced_node(FLOW_CHECKER_NAME, flow_checker, skill=FLOW_CHECKER_SKILL))
    builder.add_node(
        "compliance_checker", traced_node(COMPLIANCE_CHECKER_NAME, compliance_checker, skill=COMPLIANCE_CHECKER_SKILL)
    )
    builder.add_node("revision_router", traced_node(REVISION_ROUTER_NAME, revision_router, skill=REVISION_ROUTER_SKILL))
    builder.add_node(REVISION_MAX_LOOPS_GATE, revision_max_loops_gate)
    builder.add_node(REVIEW_COMPLETE, _mark_review_complete)

    builder.add_conditional_edges(
        "adversarial_reviewer_ensemble",
        route_after("claims_evidence_auditor"),
        {"claims_evidence_auditor": "claims_evidence_auditor", ERROR_GATE: ERROR_GATE},
    )
    builder.add_conditional_edges(
        "claims_evidence_auditor",
        route_after("flow_checker"),
        {"flow_checker": "flow_checker", ERROR_GATE: ERROR_GATE},
    )
    builder.add_conditional_edges(
        "flow_checker",
        route_after("compliance_checker"),
        {"compliance_checker": "compliance_checker", ERROR_GATE: ERROR_GATE},
    )
    builder.add_conditional_edges(
        "compliance_checker",
        route_after("revision_router"),
        {"revision_router": "revision_router", ERROR_GATE: ERROR_GATE},
    )
    builder.add_conditional_edges(
        "revision_router",
        _route_after_revision_router,
        {
            REVISION_LOOP_TARGET: REVISION_LOOP_TARGET,
            REVISION_MAX_LOOPS_GATE: REVISION_MAX_LOOPS_GATE,
            REVIEW_COMPLETE: REVIEW_COMPLETE,
            ERROR_GATE: ERROR_GATE,
        },
    )
