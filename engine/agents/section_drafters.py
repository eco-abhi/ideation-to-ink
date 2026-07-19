"""Phase 3 agent 2: draft every outlined section as a LaTeX fragment.

Writes manuscript/sections/<name>.tex and a *draft* bibliography
(manuscript/refs_draft.bib) of every citation the drafters proposed -- none of it
is trustworthy yet. citation_verifier is the only agent allowed to write the real
manuscript/refs.bib (enforced in fs_guard.ARTIFACT_WRITE_POLICY), and does so only
after independently verifying each entry against real APIs.
"""

from __future__ import annotations

from collections.abc import Iterable

from bibtexparser.bibdatabase import BibDatabase
from bibtexparser.bwriter import BibTexWriter
from pydantic import BaseModel, Field

from engine.agents.base import NodeResult
from engine.llm import call_llm_json
from engine.prompts.loader import build_system_prompt
from engine.prompts.loader import skill_ref as _skill_ref
from engine.state import Claim, PaperState
from engine.tools import fs_guard

AGENT_NAME = "section_drafters"
SKILL = _skill_ref("paper-writing-section")

DEFAULT_SECTIONS = [
    "abstract",
    "introduction",
    "related_work",
    "methods",
    "experiments",
    "results",
    "discussion",
    "conclusion",
]
DRAFT_BIB_RELPATH = "manuscript/refs_draft.bib"


class Citation(BaseModel):
    key: str
    title: str
    authors: list[str] = Field(default_factory=list)
    year: int | None = None
    doi: str | None = None
    arxiv_id: str | None = None


class DraftedSection(BaseModel):
    latex: str
    citations: list[Citation] = Field(default_factory=list)
    claims: list[str] = Field(default_factory=list)


def _skills_for_section(name: str) -> list[str]:
    skills = ["paper-writing-section", "latex-formatting"]
    if "related" in name and "work" in name:
        skills.append("related-work-writing")
    return skills


def _to_bibtex(citations: Iterable[Citation]) -> str:
    entries = []
    for c in citations:
        entry: dict[str, str] = {
            "ENTRYTYPE": "article",
            "ID": c.key,
            "title": c.title,
            "author": " and ".join(c.authors) if c.authors else "Unknown",
            "year": str(c.year) if c.year else "",
        }
        if c.doi:
            entry["doi"] = c.doi
        if c.arxiv_id:
            entry["eprint"] = c.arxiv_id
            entry["archiveprefix"] = "arXiv"
        entries.append(entry)
    db = BibDatabase()
    db.entries = entries
    return BibTexWriter().write(db)


def section_drafters(state: PaperState) -> NodeResult:
    outline = state.outline or {}
    sections: list[str] = outline.get("sections") or DEFAULT_SECTIONS
    section_plans: dict = outline.get("section_plans", {})

    all_citations: dict[str, Citation] = {}
    new_claims: list[Claim] = []
    artifacts_written: list[str] = []
    total_prompt_tokens = total_completion_tokens = 0
    model_used: str | None = None

    for section_name in sections:
        plan = section_plans.get(section_name, {})
        system_prompt = build_system_prompt(
            skills=_skills_for_section(section_name),
            local_suffix="section_drafters",
            context={
                "section_name": section_name,
                "topic": state.topic,
                "research_questions": "\n".join(f"- {q}" for q in state.research_questions) or "(none)",
                "key_points": "\n".join(f"- {p}" for p in plan.get("key_points", [])) or "(use your judgment)",
                "target_word_count": plan.get("target_word_count", 300),
            },
        )
        drafted, llm_result = call_llm_json(
            [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"Draft the {section_name} section."},
            ],
            agent_name=AGENT_NAME,
            schema=DraftedSection,
        )
        total_prompt_tokens += llm_result.prompt_tokens
        total_completion_tokens += llm_result.completion_tokens
        model_used = llm_result.model

        relpath = f"manuscript/sections/{section_name}.tex"
        fs_guard.safe_write(state.paper_id, relpath, drafted.latex, caller_agent=AGENT_NAME)
        artifacts_written.append(relpath)

        for citation in drafted.citations:
            all_citations[citation.key] = citation
        for i, claim_text in enumerate(drafted.claims):
            evidence_keys = [c.key for c in drafted.citations]
            new_claims.append(
                Claim(id=f"{section_name}-{i}", text=claim_text, evidence_refs=evidence_keys, status="unsupported")
            )

    bib_text = _to_bibtex(all_citations.values())
    fs_guard.safe_write(state.paper_id, DRAFT_BIB_RELPATH, bib_text, caller_agent=AGENT_NAME)
    artifacts_written.append(DRAFT_BIB_RELPATH)

    return NodeResult(
        update={
            "claims": new_claims,
            "artifacts": {
                **state.artifacts,
                "manuscript_sections": "manuscript/sections",
                "refs_draft": DRAFT_BIB_RELPATH,
            },
        },
        model=model_used,
        prompt_tokens=total_prompt_tokens,
        completion_tokens=total_completion_tokens,
        artifacts_written=artifacts_written,
        output_summary=f"drafted {len(sections)} sections, {len(all_citations)} proposed citations",
    )
