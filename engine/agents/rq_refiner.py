"""Phase 1 agent 3: convert topic into 2-4 falsifiable research questions + hypotheses."""

from __future__ import annotations

from pydantic import BaseModel, Field

from engine.agents.base import NodeResult
from engine.llm import call_llm_json
from engine.prompts.loader import build_system_prompt, skill_ref
from engine.state import PaperState
from engine.tools import fs_guard

AGENT_NAME = "rq_refiner"
SKILL = skill_ref("research-planning")


class ResearchQuestion(BaseModel):
    question: str
    hypothesis: str


class RQPlan(BaseModel):
    research_questions: list[ResearchQuestion] = Field(min_length=2, max_length=4)


def rq_refiner(state: PaperState) -> NodeResult:
    novelty = state.novelty_verdict or {}
    system_prompt = build_system_prompt(
        skills=["research-planning"],
        local_suffix="rq_refiner",
        context={
            "topic": state.topic,
            "novelty_rationale": novelty.get("rationale", "(no novelty verdict recorded)"),
        },
    )
    plan, llm_result = call_llm_json(
        [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": "Produce 2-4 falsifiable research questions with hypotheses."},
        ],
        agent_name=AGENT_NAME,
        schema=RQPlan,
    )

    md_lines = [f"# Research Questions: {state.topic}", ""]
    for i, rq in enumerate(plan.research_questions, start=1):
        md_lines += [f"## RQ{i}: {rq.question}", "", f"**Hypothesis:** {rq.hypothesis}", ""]
    relpath = "ideation/research_questions.md"
    fs_guard.safe_write(state.paper_id, relpath, "\n".join(md_lines), caller_agent=AGENT_NAME)

    return NodeResult(
        update={
            "research_questions": [rq.question for rq in plan.research_questions],
            "artifacts": {**state.artifacts, "research_questions": relpath},
        },
        model=llm_result.model,
        prompt_tokens=llm_result.prompt_tokens,
        completion_tokens=llm_result.completion_tokens,
        artifacts_written=[relpath],
        output_summary=f"{len(plan.research_questions)} research questions",
    )
