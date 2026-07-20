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
from engine.config import REPO_ROOT, paper_dir
from engine.graphs._registry import ERROR_GATE, route_after, traced_node
from engine.state import PaperState
from engine.tools import fs_guard
from engine.tools.venues import get_venue

CITATION_HUMAN_GATE = "citation_human_gate"
WRITING_COMPLETE = "writing_complete"
ENTRY_NODE = "structure_agent"

_DEFAULT_TEMPLATE = (
    "\\documentclass{article}\n"
    "\\usepackage[numbers]{natbib}\n"
    "\\title{%%TITLE%%}\n"
    "\\begin{document}\n"
    "\\maketitle\n"
    "%%SECTIONS%%\n"
    "\\bibliographystyle{unsrtnat}\n"
    "\\bibliography{refs}\n"
    "\\end{document}\n"
)


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


def _assemble_main_tex(state: PaperState) -> str:
    """Compose manuscript/main.tex from the venue's LaTeX template (or a minimal
    fallback) plus \\input{} lines for every drafted section, in outline order.
    Nothing else in the writing phase produces a single compilable document --
    section_drafters only writes fragments -- so this is what makes the
    "pdflatex exits 0" acceptance criterion possible to satisfy at all.
    """
    venue = get_venue(state.venue) if state.venue else None
    template_text = _DEFAULT_TEMPLATE
    if venue and venue.get("latex_template"):
        template_path = REPO_ROOT / venue["latex_template"]
        if template_path.exists():
            template_text = template_path.read_text()

    sections_dir = paper_dir(state.paper_id) / "manuscript" / "sections"
    ordered = (state.outline or {}).get("sections") or []
    available = {p.stem for p in sections_dir.glob("*.tex")} if sections_dir.exists() else set()
    ordered_available = [name for name in ordered if name in available]
    ordered_available += sorted(available - set(ordered_available))  # any section not in outline still ships

    input_lines = "\n".join(f"\\input{{sections/{name}}}" for name in ordered_available)
    title = fs_guard.latex_escape((state.outline or {}).get("title") or state.topic)

    main_tex = template_text.replace("%%TITLE%%", title).replace("%%SECTIONS%%", input_lines)
    relpath = "manuscript/main.tex"
    fs_guard.safe_write(state.paper_id, relpath, main_tex, caller_agent="writing_complete")
    return relpath


def _mark_writing_complete(state: PaperState) -> dict[str, Any]:
    relpath = _assemble_main_tex(state)
    return {"artifacts": {**state.artifacts, "main_tex": relpath}}


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
