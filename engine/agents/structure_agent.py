"""Phase 3 agent 1: venue-appropriate section outline -> state.outline."""

from __future__ import annotations

from pydantic import BaseModel, Field

from engine.agents.base import NodeResult
from engine.llm import call_llm_json
from engine.prompts.loader import build_system_prompt, skill_ref
from engine.state import PaperState
from engine.tools.venues import get_venue

AGENT_NAME = "structure_agent"
SKILL = skill_ref("ml-paper-writing")


class SectionPlan(BaseModel):
    key_points: list[str] = Field(min_length=1)
    target_word_count: int


class Outline(BaseModel):
    title: str
    sections: list[str] = Field(min_length=1)
    section_plans: dict[str, SectionPlan]


def structure_agent(state: PaperState) -> NodeResult:
    venue = get_venue(state.venue) if state.venue else None

    system_prompt = build_system_prompt(
        skills=["ml-paper-writing", "paper-schematics"],
        local_suffix="structure_agent",
        context={
            "topic": state.topic,
            "research_questions": "\n".join(f"- {q}" for q in state.research_questions) or "(none)",
            "venue_name": venue["name"] if venue else "(unspecified -- assume a top-tier ML venue)",
            "venue_family": venue["family"] if venue else "ml-conference",
            "venue_page_limit": venue.get("page_limit_main") if venue else "unknown",
            "venue_description": venue.get("description", "") if venue else "",
        },
    )
    outline, llm_result = call_llm_json(
        [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": "Produce the section outline."},
        ],
        agent_name=AGENT_NAME,
        schema=Outline,
    )

    return NodeResult(
        update={"outline": outline.model_dump()},
        model=llm_result.model,
        prompt_tokens=llm_result.prompt_tokens,
        completion_tokens=llm_result.completion_tokens,
        cost_usd=llm_result.cost_usd,
        output_summary=f"outline with {len(outline.sections)} sections",
    )
