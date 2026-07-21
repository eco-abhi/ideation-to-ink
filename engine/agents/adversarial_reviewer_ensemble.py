"""Phase 4 agent 1: 3 reviewer personas (from the venue config) actively hunting
rejection reasons, using the venue's real review criteria as the review form.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from engine.agents._shared import append_to_current_round, current_round_number, manuscript_text
from engine.agents.base import NodeResult
from engine.llm import call_llm_json
from engine.prompts.loader import build_system_prompt, skill_ref
from engine.state import PaperState
from engine.tools import fs_guard
from engine.tools.venues import get_venue

AGENT_NAME = "adversarial_reviewer_ensemble"
SKILL = skill_ref("review-ensemble")

DEFAULT_PERSONAS = [
    {"name": "The Skeptical Theorist", "focus": "Attacks unstated assumptions and missing baselines."},
    {"name": "The Reproducibility Hawk", "focus": "Checks whether every number is traceable to a described procedure."},
    {"name": "The Novelty Auditor", "focus": "Actively searches for the closest prior work the authors may have missed."},
]
DEFAULT_CRITERIA = [
    {"name": "soundness", "weight": 0.4, "description": "Are claims supported by evidence?"},
    {"name": "clarity", "weight": 0.3, "description": "Can the core idea be followed?"},
    {"name": "significance", "weight": 0.3, "description": "Does this matter to the field?"},
]


class ReviewerVerdict(BaseModel):
    overall_score: float
    recommendation: Literal["accept", "weak_accept", "borderline", "weak_reject", "reject"]
    major_concerns: list[str] = Field(default_factory=list)
    minor_concerns: list[str] = Field(default_factory=list)
    summary: str


def adversarial_reviewer_ensemble(state: PaperState) -> NodeResult:
    venue = get_venue(state.venue) if state.venue else None
    personas = venue.get("reviewer_personas", DEFAULT_PERSONAS) if venue else DEFAULT_PERSONAS
    criteria = venue.get("review_criteria", DEFAULT_CRITERIA) if venue else DEFAULT_CRITERIA
    manuscript = manuscript_text(state.paper_id)
    round_num = current_round_number(state)

    criteria_block = "\n".join(f"- {c['name']} (weight {c['weight']}): {c['description']}" for c in criteria)

    reviewer_reports: list[str] = []
    verdicts: dict[str, object] = {}
    all_major: list[str] = []
    all_minor: list[str] = []
    total_prompt_tokens = total_completion_tokens = 0
    total_cost_usd = 0.0
    model_used: str | None = None

    for i, persona in enumerate(personas, start=1):
        system_prompt = build_system_prompt(
            skills=["review-ensemble", "self-review"],
            local_suffix="adversarial_reviewer_ensemble",
            context={
                "persona_name": persona["name"],
                "persona_focus": persona["focus"],
                "venue_name": venue["name"] if venue else "(unspecified -- assume a top-tier venue)",
                "review_criteria": criteria_block,
                "manuscript": manuscript or "(manuscript is empty)",
            },
        )
        verdict, llm_result = call_llm_json(
            [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": "Review this manuscript."},
            ],
            agent_name=AGENT_NAME,
            schema=ReviewerVerdict,
        )
        total_prompt_tokens += llm_result.prompt_tokens
        total_completion_tokens += llm_result.completion_tokens
        total_cost_usd += llm_result.cost_usd or 0.0
        model_used = llm_result.model

        report_md = "\n".join(
            [
                f"# Reviewer {i}: {persona['name']}",
                "",
                f"**Recommendation:** {verdict.recommendation}  **Score:** {verdict.overall_score}",
                "",
                "## Summary",
                verdict.summary,
                "",
                "## Major Concerns",
                *(f"- {m}" for m in verdict.major_concerns),
                "",
                "## Minor Concerns",
                *(f"- {m}" for m in verdict.minor_concerns),
            ]
        )
        relpath = f"reviews/round_{round_num:02d}/reviewer_{i}.md"
        fs_guard.safe_write(state.paper_id, relpath, report_md, caller_agent=AGENT_NAME)
        reviewer_reports.append(relpath)

        verdicts[persona["name"]] = verdict.model_dump()
        all_major.extend(verdict.major_concerns)
        all_minor.extend(verdict.minor_concerns)

    updated_rounds = append_to_current_round(
        state, major=all_major, minor=all_minor, verdicts=verdicts, reviewer_reports=reviewer_reports
    )

    return NodeResult(
        update={"review_rounds": updated_rounds},
        model=model_used,
        prompt_tokens=total_prompt_tokens,
        completion_tokens=total_completion_tokens,
        cost_usd=total_cost_usd,
        artifacts_written=reviewer_reports,
        output_summary=f"round {round_num}: {len(all_major)} major, {len(all_minor)} minor across {len(personas)} reviewers",
    )
