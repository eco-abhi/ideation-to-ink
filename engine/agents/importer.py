"""Retroactive ingestion of an existing draft (skill: source-material-ingestion).

`python -m engine import <slug> --from <dir>` parses .tex/.bib (+.md/.docx
copied verbatim, not parsed) from an existing draft, scaffolds the workspace if
one doesn't exist yet, backfills PaperState (outline, claims), infers phase
(draft present -> "review", nothing found -> "ideation"), and -- if there's a
draft -- immediately runs the retroactive gates (citation_verifier,
claims_evidence_auditor, flow_checker) against reviews/round_00/, so a
pre-existing hallucinated citation or unsupported claim surfaces before this
paper ever enters the normal pipeline.

Runs these agents directly (not through the graph/checkpointer) since import is
a one-shot CLI action, not a resumable pipeline run; _apply_update replicates
the reducer-field merge semantics LangGraph would otherwise provide.
"""

from __future__ import annotations

import re
from pathlib import Path

from pydantic import BaseModel, Field

from engine.agents.citation_verifier import REPORT_RELPATH as CITATION_REPORT_RELPATH
from engine.agents.citation_verifier import citation_verifier
from engine.agents.claims_evidence_auditor import claims_evidence_auditor
from engine.agents.flow_checker import flow_checker
from engine.config import paper_dir
from engine.llm import call_llm_json
from engine.prompts.loader import build_system_prompt
from engine.state import Claim, PaperState, ReviewRound
from engine.tools import fs_guard
from engine.tools.workspace import load_paper_yaml, save_paper_yaml, scaffold_workspace

AGENT_NAME = "importer"

_REDUCER_FIELDS = {"claims", "citation_records", "review_rounds", "errors"}


def _apply_update(state: PaperState, update: dict) -> PaperState:
    merged: dict = {}
    for key, value in update.items():
        merged[key] = [*getattr(state, key), *value] if key in _REDUCER_FIELDS else value
    return state.model_copy(update=merged)


class ExtractedClaims(BaseModel):
    claims: list[str] = Field(default_factory=list)


def _extract_title(tex_text: str) -> str | None:
    match = re.search(r"\\title\{([^}]*)\}", tex_text)
    return match.group(1).strip() if match else None


def _copy_sections(source_dir: Path, paper_id: str) -> list[str]:
    """Copy every .tex file under source_dir into manuscript/sections/, keyed by
    filename stem. Best-effort: does not attempt to split a monolithic main.tex
    into logical sections.
    """
    section_names = []
    for tex_file in sorted(source_dir.rglob("*.tex")):
        relpath = f"manuscript/sections/{tex_file.stem}.tex"
        fs_guard.safe_write(paper_id, relpath, tex_file.read_text(errors="replace"), caller_agent=AGENT_NAME)
        section_names.append(tex_file.stem)
    return section_names


def _copy_bibliographies(source_dir: Path, paper_id: str) -> bool:
    """Concatenate every .bib file into manuscript/refs_draft.bib -- an imported
    bibliography is exactly as untrusted as one section_drafters proposed;
    citation_verifier is what earns entries a place in the real refs.bib.
    """
    bib_files = sorted(source_dir.rglob("*.bib"))
    if not bib_files:
        return False
    combined = "\n\n".join(f.read_text(errors="replace") for f in bib_files)
    fs_guard.safe_write(paper_id, "manuscript/refs_draft.bib", combined, caller_agent=AGENT_NAME)
    return True


def _copy_other_source_files(source_dir: Path, paper_id: str) -> None:
    """.md/.docx aren't parsed for backfill -- copied verbatim into
    imported_source/ so nothing passed via --from is silently dropped.
    """
    for f in sorted(source_dir.rglob("*.md")):
        fs_guard.safe_write(
            paper_id, f"imported_source/{f.name}", f.read_text(errors="replace"), caller_agent=AGENT_NAME
        )
    for f in sorted(source_dir.rglob("*.docx")):
        target = paper_dir(paper_id) / "imported_source" / f.name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(f.read_bytes())


def _extract_claims_for_section(section_name: str, latex: str) -> list[Claim]:
    system_prompt = build_system_prompt(
        local_suffix="importer", context={"section_name": section_name, "latex": latex[:6000]}
    )
    extracted, _ = call_llm_json(
        [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": "Extract the claims."},
        ],
        agent_name=AGENT_NAME,
        schema=ExtractedClaims,
    )
    raw_groups = re.findall(r"\\cite\{([^}]*)\}", latex)
    evidence_refs = sorted({key.strip() for group in raw_groups for key in group.split(",") if key.strip()})
    return [
        Claim(id=f"{section_name}-{i}", text=text, evidence_refs=evidence_refs, status="unsupported")
        for i, text in enumerate(extracted.claims)
    ]


def import_paper(slug: str, *, source_dir: str) -> PaperState:
    src = Path(source_dir)
    if not src.exists():
        raise FileNotFoundError(f"--from {source_dir} does not exist")

    pdir = paper_dir(slug)
    if not pdir.exists():
        title = None
        for tex_file in sorted(src.rglob("*.tex")):
            title = _extract_title(tex_file.read_text(errors="replace"))
            if title:
                break
        scaffold_workspace(slug, topic=title or slug.replace("-", " "), phase="ideation", status="imported")

    section_names = _copy_sections(src, slug)
    has_bib = _copy_bibliographies(src, slug)
    _copy_other_source_files(src, slug)

    phase = "review" if section_names else "ideation"

    claims: list[Claim] = []
    for name in section_names:
        section_text = (pdir / "manuscript" / "sections" / f"{name}.tex").read_text()
        claims.extend(_extract_claims_for_section(name, section_text))

    doc = load_paper_yaml(slug)
    doc["phase"] = phase
    doc["status"] = "imported"
    save_paper_yaml(slug, doc)

    state = PaperState(
        paper_id=slug,
        topic=doc["topic"],
        venue=doc.get("venue"),
        phase=phase,
        outline={"sections": section_names, "section_plans": {}} if section_names else None,
        claims=claims,
    )

    if phase != "review":
        return state  # nothing to retroactively review yet

    retro_state = state.model_copy(update={"review_rounds": [ReviewRound(round=0)]})

    if has_bib:
        cv_result = citation_verifier(retro_state)
        retro_state = _apply_update(retro_state, cv_result.update)
        # citation_verifier always writes to manuscript/ (it's normally a writing-phase
        # agent); mirror the report into reviews/round_00/ too so every retroactive
        # import finding lives in one predictable place.
        report_text = (paper_dir(slug) / CITATION_REPORT_RELPATH).read_text()
        fs_guard.safe_write(
            slug, f"reviews/round_00/{Path(CITATION_REPORT_RELPATH).name}", report_text, caller_agent=AGENT_NAME
        )

    cea_result = claims_evidence_auditor(retro_state)
    retro_state = _apply_update(retro_state, cea_result.update)

    fc_result = flow_checker(retro_state)
    retro_state = _apply_update(retro_state, fc_result.update)

    return retro_state
