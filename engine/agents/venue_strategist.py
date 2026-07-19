"""Phase 1 agent 4: rank configured venues (shared/venues/*.yaml) and write the choice to paper.yaml."""

from __future__ import annotations

import yaml
from pydantic import BaseModel

from engine.agents.base import NodeResult
from engine.config import paper_dir
from engine.llm import call_llm_json
from engine.prompts.loader import build_system_prompt, skill_ref
from engine.state import PaperState
from engine.tools import fs_guard
from engine.tools.venues import list_venues

AGENT_NAME = "venue_strategist"
SKILL = skill_ref("venue-submission-strategy")


class VenueRanking(BaseModel):
    slug: str
    rank: int
    rationale: str


class VenueStrategy(BaseModel):
    rankings: list[VenueRanking]
    chosen_slug: str
    chosen_rationale: str


def _venues_block(venues: list[dict]) -> str:
    return "\n\n".join(
        f"- slug: {v['slug']}\n"
        f"  name: {v['name']}\n"
        f"  family: {v['family']}\n"
        f"  scope_keywords: {', '.join(v.get('scope_keywords', []))}\n"
        f"  page_limit_main: {v.get('page_limit_main')}\n"
        f"  typical_deadline_month: {v.get('typical_deadline_month')}"
        for v in venues
    )


def venue_strategist(state: PaperState) -> NodeResult:
    venues = list_venues()
    if not venues:
        raise ValueError("no venue configs found under shared/venues/*.yaml")

    system_prompt = build_system_prompt(
        skills=["venue-submission-strategy"],
        local_suffix="venue_strategist",
        context={
            "topic": state.topic,
            "research_questions": "\n".join(f"- {q}" for q in state.research_questions) or "(none yet)",
            "deadline": str(state.deadline) if state.deadline else "(not set)",
            "venues": _venues_block(venues),
        },
    )
    strategy, llm_result = call_llm_json(
        [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": "Rank the venues and choose one."},
        ],
        agent_name=AGENT_NAME,
        schema=VenueStrategy,
    )

    valid_slugs = {v["slug"] for v in venues}
    if strategy.chosen_slug not in valid_slugs:
        raise ValueError(
            f"venue_strategist chose {strategy.chosen_slug!r}, not one of the configured venues {valid_slugs}"
        )

    yaml_path = paper_dir(state.paper_id) / "paper.yaml"
    doc = yaml.safe_load(yaml_path.read_text()) if yaml_path.exists() else {}
    doc["venue"] = strategy.chosen_slug
    doc["venue_rationale"] = strategy.chosen_rationale
    doc["venue_rankings"] = [r.model_dump() for r in strategy.rankings]
    fs_guard.safe_write(state.paper_id, "paper.yaml", yaml.safe_dump(doc, sort_keys=False), caller_agent=AGENT_NAME)

    return NodeResult(
        update={"venue": strategy.chosen_slug},
        model=llm_result.model,
        prompt_tokens=llm_result.prompt_tokens,
        completion_tokens=llm_result.completion_tokens,
        artifacts_written=["paper.yaml"],
        output_summary=f"chose venue={strategy.chosen_slug}",
    )
