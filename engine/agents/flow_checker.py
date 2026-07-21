"""Phase 4 agent 3: reconstruct the outline the draft actually implements, diff
against the intended outline, flag drift and orphaned sections.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from engine.agents._shared import append_to_current_round, current_round_number, manuscript_text
from engine.agents.base import NodeResult
from engine.config import paper_dir
from engine.llm import call_llm_json
from engine.prompts.loader import build_system_prompt, skill_ref
from engine.state import PaperState
from engine.tools import fs_guard

AGENT_NAME = "flow_checker"
SKILL = skill_ref("reverse-outline-flow-check")


class ReconstructedOutline(BaseModel):
    sections_found: list[str] = Field(default_factory=list)
    drift_notes: list[str] = Field(default_factory=list)
    orphaned_sections: list[str] = Field(default_factory=list)


def flow_checker(state: PaperState) -> NodeResult:
    intended_sections: list[str] = (state.outline or {}).get("sections", [])
    sections_dir = paper_dir(state.paper_id) / "manuscript" / "sections"
    actual_sections = sorted(p.stem for p in sections_dir.glob("*.tex")) if sections_dir.exists() else []
    manuscript = manuscript_text(state.paper_id)
    round_num = current_round_number(state)

    system_prompt = build_system_prompt(
        skills=["reverse-outline-flow-check", "long-form-manuscript-polish"],
        local_suffix="flow_checker",
        context={
            "intended_sections": ", ".join(intended_sections) or "(no outline recorded)",
            "manuscript": manuscript or "(manuscript is empty)",
        },
    )
    recon, llm_result = call_llm_json(
        [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": "Reconstruct the outline and flag drift."},
        ],
        agent_name=AGENT_NAME,
        schema=ReconstructedOutline,
    )

    missing = sorted(set(intended_sections) - set(actual_sections))
    extra = sorted(set(actual_sections) - set(intended_sections))

    major = [f"Section '{s}' is in the outline but missing from the draft" for s in missing]
    minor = (
        [f"Section '{s}' exists in the draft but isn't in the outline" for s in extra]
        + [f"Drift: {note}" for note in recon.drift_notes]
        + [f"Orphaned: {note}" for note in recon.orphaned_sections]
    )

    relpath = f"reviews/round_{round_num:02d}/flow_check.md"
    report = "\n".join(
        [
            "# Reverse-Outline Flow Check",
            "",
            f"Sections found: {', '.join(actual_sections) or '(none)'}",
            f"Missing from draft: {', '.join(missing) or '(none)'}",
            f"Not in outline: {', '.join(extra) or '(none)'}",
            "",
            "## Drift",
            *(f"- {n}" for n in recon.drift_notes),
            "",
            "## Orphaned",
            *(f"- {n}" for n in recon.orphaned_sections),
        ]
    )
    fs_guard.safe_write(state.paper_id, relpath, report, caller_agent=AGENT_NAME)

    return NodeResult(
        update={"review_rounds": append_to_current_round(state, major=major, minor=minor)},
        model=llm_result.model,
        prompt_tokens=llm_result.prompt_tokens,
        completion_tokens=llm_result.completion_tokens,
        cost_usd=llm_result.cost_usd,
        artifacts_written=[relpath],
        output_summary=f"round {round_num}: {len(missing)} missing sections, {len(recon.drift_notes)} drift notes",
    )
