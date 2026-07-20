"""Phase 2 agent 1: propose design/baselines/ablations/metrics -> experiments/DESIGN.md.

graphs/experiments.py adds a human-approval interrupt right after this node.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from engine.agents.base import NodeResult
from engine.llm import call_llm_json
from engine.prompts.loader import build_system_prompt, skill_ref
from engine.state import PaperState
from engine.tools import fs_guard

AGENT_NAME = "methodology_designer"
SKILL = skill_ref("research-planning")

DESIGN_RELPATH = "experiments/DESIGN.md"


class ExperimentDesign(BaseModel):
    methodology: str
    baselines: list[str] = Field(min_length=1)
    ablations: list[str] = Field(min_length=1)
    metrics: list[str] = Field(min_length=1)
    datasets: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)


def methodology_designer(state: PaperState) -> NodeResult:
    system_prompt = build_system_prompt(
        skills=["research-planning", "reporting-guidelines-check"],
        local_suffix="methodology_designer",
        context={
            "topic": state.topic,
            "research_questions": "\n".join(f"- {q}" for q in state.research_questions) or "(none recorded)",
        },
    )
    design, llm_result = call_llm_json(
        [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": "Propose the experimental design."},
        ],
        agent_name=AGENT_NAME,
        schema=ExperimentDesign,
    )

    md = "\n".join(
        [
            "# Experiment Design",
            "",
            "## Methodology",
            design.methodology,
            "",
            "## Baselines",
            *(f"- {b}" for b in design.baselines),
            "",
            "## Ablations",
            *(f"- {a}" for a in design.ablations),
            "",
            "## Metrics",
            *(f"- {m}" for m in design.metrics),
            "",
            "## Datasets",
            *(f"- {d}" for d in design.datasets),
            "",
            "## Risks",
            *(f"- {r}" for r in design.risks),
        ]
    )
    fs_guard.safe_write(state.paper_id, DESIGN_RELPATH, md, caller_agent=AGENT_NAME)

    return NodeResult(
        update={"artifacts": {**state.artifacts, "design": DESIGN_RELPATH}},
        model=llm_result.model,
        prompt_tokens=llm_result.prompt_tokens,
        completion_tokens=llm_result.completion_tokens,
        artifacts_written=[DESIGN_RELPATH],
        output_summary=f"{len(design.baselines)} baselines, {len(design.ablations)} ablations, {len(design.metrics)} metrics",
    )
