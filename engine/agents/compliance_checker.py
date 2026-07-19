"""Phase 4 agent 4: anonymization/page-limit/formatting/checklist compliance,
emitting a quantitative pre-submission score as the phase-4 exit metric.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from engine.agents._shared import append_to_current_round, current_round_number, manuscript_text
from engine.agents.base import NodeResult
from engine.llm import call_llm_json
from engine.prompts.loader import build_system_prompt, skill_ref
from engine.state import PaperState
from engine.tools import fs_guard
from engine.tools.venues import get_venue

AGENT_NAME = "compliance_checker"
SKILL = skill_ref("submission-qa-gate")

DEFAULT_CHECKLIST = [
    "No author-identifying information in the main text",
    "All claims traceable to a table, figure, or citation",
    "Limitations discussed",
]


class ComplianceItem(BaseModel):
    item: str
    passed: bool
    notes: str


class ComplianceReport(BaseModel):
    items: list[ComplianceItem] = Field(default_factory=list)
    score: float


def compliance_checker(state: PaperState) -> NodeResult:
    venue = get_venue(state.venue) if state.venue else None
    checklist = venue.get("checklist_items", DEFAULT_CHECKLIST) if venue else DEFAULT_CHECKLIST
    manuscript = manuscript_text(state.paper_id)
    round_num = current_round_number(state)

    system_prompt = build_system_prompt(
        skills=["submission-qa-gate", "reporting-guidelines-check", "manuscript-scorecard"],
        local_suffix="compliance_checker",
        context={
            "venue_name": venue["name"] if venue else "(unspecified)",
            "anonymization": venue.get("anonymization") if venue else "unknown",
            "page_limit": venue.get("page_limit_main") if venue else "unknown",
            "checklist": "\n".join(f"- {c}" for c in checklist),
            "manuscript": manuscript or "(manuscript is empty)",
        },
    )
    report, llm_result = call_llm_json(
        [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": "Score submission compliance."},
        ],
        agent_name=AGENT_NAME,
        schema=ComplianceReport,
    )

    failed = [f"Compliance: {i.item} — {i.notes}" for i in report.items if not i.passed]

    scorecard_md = "\n".join(
        [
            "# Compliance Scorecard",
            "",
            f"**Score:** {report.score:.2f}",
            "",
            *(f"- [{'x' if i.passed else ' '}] {i.item} — {i.notes}" for i in report.items),
        ]
    )
    relpath = f"reviews/round_{round_num:02d}/compliance_scorecard.md"
    fs_guard.safe_write(state.paper_id, relpath, scorecard_md, caller_agent=AGENT_NAME)

    return NodeResult(
        update={
            "review_rounds": append_to_current_round(
                state, minor=failed, verdicts={"compliance_score": report.score}
            )
        },
        model=llm_result.model,
        prompt_tokens=llm_result.prompt_tokens,
        completion_tokens=llm_result.completion_tokens,
        artifacts_written=[relpath],
        output_summary=f"round {round_num}: compliance score={report.score:.2f}, {len(failed)} failed items",
    )
