"""Cross-cutting agent #17: summarize resolved review rounds + completed-phase
state into a compact ledger artifact (skills: paper-memory-ledger,
paper-session-compaction).

Honest limitation: LangGraph's operator.add reducer on claims/citation_records/
review_rounds makes those fields append-only from any single node's return
value -- a node can't shrink them by returning a smaller list (the reducer
just concatenates on top). So this agent writes a human-readable *summary*
artifact and reports whether live state has grown past a size threshold; it
does not truncate the reducer-backed fields in place. PaperState.effective_*()
already keeps the *logical* view bounded (deduped by id/round/key) even as the
raw log grows, which is what matters for correctness -- this agent is about
having a readable ledger available without replaying the full accumulated
state or provenance/run_log.jsonl.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from engine.agents.base import NodeResult
from engine.llm import call_llm_json
from engine.prompts.loader import build_system_prompt, skill_ref
from engine.state import PaperState
from engine.tools import fs_guard

AGENT_NAME = "state_compaction"
SKILL = skill_ref("paper-memory-ledger")

LEDGER_RELPATH = "provenance/state_ledger.md"
DEFAULT_SIZE_THRESHOLD_BYTES = 50_000


class RoundSummary(BaseModel):
    round: int
    summary: str


class CompactionLedger(BaseModel):
    round_summaries: list[RoundSummary] = Field(default_factory=list)
    overall_summary: str


def should_compact(state: PaperState, *, threshold_bytes: int = DEFAULT_SIZE_THRESHOLD_BYTES) -> bool:
    return len(state.model_dump_json()) > threshold_bytes


def state_compaction(state: PaperState) -> NodeResult:
    rounds = state.effective_review_rounds()
    round_lines = (
        "\n".join(
            f"- round {r.round}: {len(r.major_concerns)} major / {len(r.minor_concerns)} minor, resolved={r.resolved}"
            for r in rounds
        )
        or "(no review rounds yet)"
    )

    system_prompt = build_system_prompt(
        skills=["paper-memory-ledger"],
        local_suffix="state_compaction",
        context={
            "topic": state.topic,
            "novelty_verdict": (state.novelty_verdict or {}).get("verdict", "(none)"),
            "venue": state.venue or "(unset)",
            "research_questions": "\n".join(f"- {q}" for q in state.research_questions) or "(none)",
            "round_summaries": round_lines,
        },
    )
    ledger, llm_result = call_llm_json(
        [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": "Produce the state ledger."},
        ],
        agent_name=AGENT_NAME,
        schema=CompactionLedger,
    )

    claims = state.effective_claims()
    citation_records = state.effective_citation_records()
    supported = sum(1 for c in claims if c.status == "supported")
    verified = sum(1 for r in citation_records if r.status == "verified")

    md = "\n".join(
        [
            f"# State Ledger: {state.topic}",
            "",
            f"Phase: {state.phase}  |  Venue: {state.venue or '(unset)'}  |  "
            f"Revision loops used: {state.revision_loop_count}",
            "",
            f"Claims: {supported}/{len(claims)} supported.  "
            f"Citations: {verified}/{len(citation_records)} verified.",
            "",
            "## Overall",
            ledger.overall_summary,
            "",
            "## Review Rounds",
            *(f"### Round {r.round}\n{r.summary}" for r in ledger.round_summaries),
        ]
    )
    fs_guard.safe_write(state.paper_id, LEDGER_RELPATH, md, caller_agent=AGENT_NAME)

    live_size = len(state.model_dump_json())
    over_under = "over" if should_compact(state) else "under"
    return NodeResult(
        update={"artifacts": {**state.artifacts, "state_ledger": LEDGER_RELPATH}},
        model=llm_result.model,
        prompt_tokens=llm_result.prompt_tokens,
        completion_tokens=llm_result.completion_tokens,
        cost_usd=llm_result.cost_usd,
        artifacts_written=[LEDGER_RELPATH],
        output_summary=(
            f"ledger written ({len(rounds)} rounds); live state {live_size}B "
            f"({over_under} the {DEFAULT_SIZE_THRESHOLD_BYTES}B threshold)"
        ),
    )
