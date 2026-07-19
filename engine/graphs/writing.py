"""Phase 3 (Writing): structure_agent -> section_drafters -> citation_verifier ->
[human gate iff suspicious citations exist] -> writing_complete.

Mirrors graphs/ideation.py's shape: add_writing_nodes registers onto a shared
StateGraph; graphs/master.py owns what comes before/after.
"""

from __future__ import annotations

from typing import Any

import bibtexparser
from bibtexparser.bibdatabase import BibDatabase
from bibtexparser.bwriter import BibTexWriter
from langgraph.types import interrupt

from engine.agents.citation_verifier import AGENT_NAME as CITATION_VERIFIER_NAME
from engine.agents.citation_verifier import DRAFT_BIB_RELPATH, FINAL_BIB_RELPATH, citation_verifier
from engine.agents.citation_verifier import SKILL as CITATION_VERIFIER_SKILL
from engine.agents.section_drafters import AGENT_NAME as SECTION_DRAFTERS_NAME
from engine.agents.section_drafters import SKILL as SECTION_DRAFTERS_SKILL
from engine.agents.section_drafters import section_drafters
from engine.agents.structure_agent import AGENT_NAME as STRUCTURE_AGENT_NAME
from engine.agents.structure_agent import SKILL as STRUCTURE_AGENT_SKILL
from engine.agents.structure_agent import structure_agent
from engine.config import paper_dir
from engine.graphs._registry import ERROR_GATE, route_after, traced_node
from engine.state import PaperState
from engine.tools import fs_guard

CITATION_HUMAN_GATE = "citation_human_gate"
WRITING_COMPLETE = "writing_complete"
ENTRY_NODE = "structure_agent"


def citation_human_gate(state: PaperState) -> dict[str, Any]:
    """Only pauses if citation_verifier left `suspicious` entries -- verified-only
    and no-suspicious-entries runs pass straight through with no interrupt.
    """
    suspicious = [r for r in state.effective_citation_records() if r.status == "suspicious"]
    if not suspicious:
        return {}

    decision = interrupt(
        {
            "type": "suspicious_citations",
            "paper_id": state.paper_id,
            "suspicious": [r.model_dump() for r in suspicious],
            "instructions": (
                "Resume with {'approve': ['key1', ...]} to include specific suspicious "
                "entries in refs.bib despite the classifier's doubt, or {'approve': []} "
                "(or nothing) to leave them excluded."
            ),
        }
    )
    approved_keys = set((decision or {}).get("approve", [])) if isinstance(decision, dict) else set()
    if not approved_keys:
        return {}

    draft_db = bibtexparser.loads((paper_dir(state.paper_id) / DRAFT_BIB_RELPATH).read_text())
    approved_entries = [e for e in draft_db.entries if e["ID"] in approved_keys]
    if not approved_entries:
        return {}

    final_path = paper_dir(state.paper_id) / FINAL_BIB_RELPATH
    existing_db = bibtexparser.loads(final_path.read_text()) if final_path.exists() else BibDatabase()
    existing_ids = {e["ID"] for e in existing_db.entries}
    merged_entries = existing_db.entries + [e for e in approved_entries if e["ID"] not in existing_ids]

    out_db = BibDatabase()
    out_db.entries = merged_entries
    fs_guard.safe_write(
        state.paper_id, FINAL_BIB_RELPATH, BibTexWriter().write(out_db), caller_agent=CITATION_VERIFIER_NAME
    )

    updated_records = [
        r.model_copy(
            update={"status": "verified", "rationale": r.rationale + " (human-approved despite suspicious classification)"}
        )
        for r in suspicious
        if r.bib_key in approved_keys
    ]
    return {"bib_keys": [e["ID"] for e in merged_entries], "citation_records": updated_records}


def _mark_writing_complete(state: PaperState) -> dict[str, Any]:
    return {}


def add_writing_nodes(builder: Any) -> None:
    builder.add_node(
        "structure_agent", traced_node(STRUCTURE_AGENT_NAME, structure_agent, skill=STRUCTURE_AGENT_SKILL)
    )
    builder.add_node(
        "section_drafters", traced_node(SECTION_DRAFTERS_NAME, section_drafters, skill=SECTION_DRAFTERS_SKILL)
    )
    builder.add_node(
        "citation_verifier", traced_node(CITATION_VERIFIER_NAME, citation_verifier, skill=CITATION_VERIFIER_SKILL)
    )
    builder.add_node(CITATION_HUMAN_GATE, citation_human_gate)
    builder.add_node(WRITING_COMPLETE, _mark_writing_complete)

    builder.add_conditional_edges(
        "structure_agent",
        route_after("section_drafters"),
        {"section_drafters": "section_drafters", ERROR_GATE: ERROR_GATE},
    )
    builder.add_conditional_edges(
        "section_drafters",
        route_after("citation_verifier"),
        {"citation_verifier": "citation_verifier", ERROR_GATE: ERROR_GATE},
    )
    builder.add_conditional_edges(
        "citation_verifier",
        route_after(CITATION_HUMAN_GATE),
        {CITATION_HUMAN_GATE: CITATION_HUMAN_GATE, ERROR_GATE: ERROR_GATE},
    )
    builder.add_edge(CITATION_HUMAN_GATE, WRITING_COMPLETE)
