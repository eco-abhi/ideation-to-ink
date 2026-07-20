"""Standalone audit agent (skill: rebuttal-writing): draft a point-by-point
rebuttal to the latest review round's concerns. Invoked via
`python -m engine check --agent rebuttal_writer` for post-submission rounds --
outside the automated pre-review loop, which is what revision_router already
handles for pre-submission iteration.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from engine.agents.base import NodeResult
from engine.llm import call_llm_json
from engine.prompts.loader import build_system_prompt, skill_ref
from engine.state import PaperState
from engine.tools import fs_guard

AGENT_NAME = "rebuttal_writer"
SKILL = skill_ref("rebuttal-writing")


class RebuttalPoint(BaseModel):
    concern: str
    response: str


class Rebuttal(BaseModel):
    summary: str
    points: list[RebuttalPoint] = Field(default_factory=list)


def rebuttal_writer(state: PaperState) -> NodeResult:
    rounds = state.effective_review_rounds()
    if not rounds:
        raise ValueError("no review rounds recorded to write a rebuttal for")
    latest = max(rounds, key=lambda r: r.round)
    concerns = [*latest.major_concerns, *latest.minor_concerns]
    if not concerns:
        raise ValueError(f"round {latest.round} has no concerns to rebut")

    system_prompt = build_system_prompt(
        skills=["rebuttal-writing"],
        local_suffix="rebuttal_writer",
        context={"concerns": "\n".join(f"- {c}" for c in concerns)},
    )
    rebuttal, llm_result = call_llm_json(
        [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": "Write the rebuttal."},
        ],
        agent_name=AGENT_NAME,
        schema=Rebuttal,
    )

    md = "\n\n".join(
        [
            "# Rebuttal",
            rebuttal.summary,
            *[f"**Concern:** {p.concern}\n\n**Response:** {p.response}" for p in rebuttal.points],
        ]
    )
    relpath = f"reviews/round_{latest.round:02d}/rebuttal.md"
    fs_guard.safe_write(state.paper_id, relpath, md, caller_agent=AGENT_NAME)

    return NodeResult(
        update={},
        model=llm_result.model,
        prompt_tokens=llm_result.prompt_tokens,
        completion_tokens=llm_result.completion_tokens,
        artifacts_written=[relpath],
        output_summary=f"rebuttal for round {latest.round}: {len(concerns)} concerns addressed",
    )
