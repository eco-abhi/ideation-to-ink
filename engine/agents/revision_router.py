"""Phase 4 agent 5: decide whether the review round converged, needs another
revision loop (capped at MAX_REVISION_LOOPS), or has exhausted the loop budget.

The routing decision itself is made here (in state); graphs/review.py's
conditional edge just reads what this node decided. When another loop is
needed, this agent (paper-revision skill) turns the round's major concerns into
a concrete per-section revision_brief.md that section_drafters reads on its
next pass.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from engine.agents._shared import current_round_number, get_current_round
from engine.agents.base import NodeResult
from engine.config import MAX_REVISION_LOOPS
from engine.llm import call_llm_json
from engine.prompts.loader import build_system_prompt, skill_ref
from engine.state import PaperState, ReviewRound
from engine.tools import fs_guard

AGENT_NAME = "revision_router"
SKILL = skill_ref("paper-revision")


class RevisionBrief(BaseModel):
    section_instructions: dict[str, str] = Field(default_factory=dict)


def revision_router(state: PaperState) -> NodeResult:
    round_num = current_round_number(state)
    current = get_current_round(state)
    major = current.major_concerns if current else []

    if not major:
        resolved = (
            current.model_copy(update={"resolved": True}) if current else ReviewRound(round=round_num, resolved=True)
        )
        return NodeResult(
            update={"review_rounds": [resolved], "phase": "done"},
            output_summary=f"round {round_num} converged with no major concerns; phase=done",
        )

    if state.revision_loop_count >= MAX_REVISION_LOOPS:
        return NodeResult(
            update={},
            output_summary=(
                f"revision loop cap ({MAX_REVISION_LOOPS}) reached with {len(major)} major concerns remaining"
            ),
        )

    sections = ", ".join((state.outline or {}).get("sections", [])) or "(no outline recorded)"
    system_prompt = build_system_prompt(
        skills=["paper-revision"],
        local_suffix="revision_router",
        context={"sections": sections, "major_concerns": "\n".join(f"- {m}" for m in major)},
    )
    brief, llm_result = call_llm_json(
        [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": "Produce the revision brief."},
        ],
        agent_name=AGENT_NAME,
        schema=RevisionBrief,
    )

    brief_md = "\n\n".join(
        [f"# Revision Brief (round {round_num})", *(f"## {s}\n{instr}" for s, instr in brief.section_instructions.items())]
    )
    relpath = f"reviews/round_{round_num:02d}/revision_brief.md"
    fs_guard.safe_write(state.paper_id, relpath, brief_md, caller_agent=AGENT_NAME)

    next_loop = state.revision_loop_count + 1
    return NodeResult(
        update={"revision_loop_count": next_loop, "phase": "revision"},
        model=llm_result.model,
        prompt_tokens=llm_result.prompt_tokens,
        completion_tokens=llm_result.completion_tokens,
        artifacts_written=[relpath],
        output_summary=f"round {round_num}: {len(major)} major concerns -> revision brief, loop {next_loop}/{MAX_REVISION_LOOPS}",
    )
