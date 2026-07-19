"""Phase 1 (Ideation): literature_scout -> novelty_checker -> [human gate] -> rq_refiner -> venue_strategist.

`add_ideation_nodes` registers this phase's nodes and internal edges onto a shared
StateGraph -- it does not compile or wire what comes before/after it. graphs/master.py
owns the full cross-phase topology and adds the edge into "ideation_complete" (entry)
and out of it (exit), per the plan's rationale for not nesting true LangGraph subgraphs
(the revision loop needs to jump back into a node the writing phase owns).
"""

from __future__ import annotations

from typing import Any

from langgraph.graph import END
from langgraph.types import interrupt

from engine.agents.literature_scout import AGENT_NAME as LITERATURE_SCOUT_NAME
from engine.agents.literature_scout import SKILL as LITERATURE_SCOUT_SKILL
from engine.agents.literature_scout import literature_scout
from engine.agents.novelty_checker import AGENT_NAME as NOVELTY_CHECKER_NAME
from engine.agents.novelty_checker import SKILL as NOVELTY_CHECKER_SKILL
from engine.agents.novelty_checker import novelty_checker
from engine.agents.rq_refiner import AGENT_NAME as RQ_REFINER_NAME
from engine.agents.rq_refiner import SKILL as RQ_REFINER_SKILL
from engine.agents.rq_refiner import rq_refiner
from engine.agents.venue_strategist import AGENT_NAME as VENUE_STRATEGIST_NAME
from engine.agents.venue_strategist import SKILL as VENUE_STRATEGIST_SKILL
from engine.agents.venue_strategist import venue_strategist
from engine.graphs._registry import ERROR_GATE, route_after, traced_node
from engine.state import PaperState

NOVELTY_HUMAN_GATE = "novelty_human_gate"
IDEATION_COMPLETE = "ideation_complete"
ENTRY_NODE = "literature_scout"


def novelty_human_gate(state: PaperState) -> dict[str, Any]:
    """Always pauses after novelty_checker (per the HITL spec), even on PROCEED, so a
    human can catch a bad verdict before more compute is spent. Resume with
    {"decision": "proceed"} or {"decision": "stop"}; omitting a decision defaults to
    the model's own verdict (STOP stays stopped, PROCEED/PIVOT continue).
    """
    verdict = state.novelty_verdict or {}
    decision = interrupt(
        {
            "type": "novelty_verdict",
            "paper_id": state.paper_id,
            "verdict": verdict.get("verdict"),
            "score": verdict.get("score"),
            "rationale": verdict.get("rationale"),
            "instructions": "Resume with {'decision': 'proceed'} or {'decision': 'stop'}.",
        }
    )
    default_decision = "stop" if verdict.get("verdict") == "STOP" else "proceed"
    chosen = decision.get("decision", default_decision) if isinstance(decision, dict) else default_decision
    return {"novelty_verdict": {**verdict, "human_decision": chosen}}


def _route_after_novelty_gate(state: PaperState) -> str:
    decision = (state.novelty_verdict or {}).get("human_decision")
    return "rq_refiner" if decision == "proceed" else END


def _mark_ideation_complete(state: PaperState) -> dict[str, Any]:
    return {}


def add_ideation_nodes(builder: Any) -> None:
    builder.add_node(
        "literature_scout", traced_node(LITERATURE_SCOUT_NAME, literature_scout, skill=LITERATURE_SCOUT_SKILL)
    )
    builder.add_node(
        "novelty_checker", traced_node(NOVELTY_CHECKER_NAME, novelty_checker, skill=NOVELTY_CHECKER_SKILL)
    )
    builder.add_node(NOVELTY_HUMAN_GATE, novelty_human_gate)
    builder.add_node("rq_refiner", traced_node(RQ_REFINER_NAME, rq_refiner, skill=RQ_REFINER_SKILL))
    builder.add_node(
        "venue_strategist", traced_node(VENUE_STRATEGIST_NAME, venue_strategist, skill=VENUE_STRATEGIST_SKILL)
    )
    builder.add_node(IDEATION_COMPLETE, _mark_ideation_complete)

    builder.add_conditional_edges(
        "literature_scout",
        route_after("novelty_checker"),
        {"novelty_checker": "novelty_checker", ERROR_GATE: ERROR_GATE},
    )
    builder.add_conditional_edges(
        "novelty_checker",
        route_after(NOVELTY_HUMAN_GATE),
        {NOVELTY_HUMAN_GATE: NOVELTY_HUMAN_GATE, ERROR_GATE: ERROR_GATE},
    )
    builder.add_conditional_edges(
        NOVELTY_HUMAN_GATE,
        _route_after_novelty_gate,
        {"rq_refiner": "rq_refiner", END: END},
    )
    builder.add_conditional_edges(
        "rq_refiner",
        route_after("venue_strategist"),
        {"venue_strategist": "venue_strategist", ERROR_GATE: ERROR_GATE},
    )
    builder.add_conditional_edges(
        "venue_strategist",
        route_after(IDEATION_COMPLETE),
        {IDEATION_COMPLETE: IDEATION_COMPLETE, ERROR_GATE: ERROR_GATE},
    )
