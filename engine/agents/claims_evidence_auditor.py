"""Phase 4 agent 2: map every claim to evidence; unsupported claim = major concern."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from engine.agents._shared import append_to_current_round, current_round_number
from engine.agents.base import NodeResult
from engine.llm import call_llm_json
from engine.prompts.loader import build_system_prompt, skill_ref
from engine.state import PaperState

AGENT_NAME = "claims_evidence_auditor"
SKILL = skill_ref("claim-evidence-map")


class ClaimAudit(BaseModel):
    claim_id: str
    status: Literal["supported", "unsupported", "disputed"]
    rationale: str


class ClaimsAuditResult(BaseModel):
    audits: list[ClaimAudit] = Field(default_factory=list)


def claims_evidence_auditor(state: PaperState) -> NodeResult:
    claims = state.effective_claims()
    round_num = current_round_number(state)

    if not claims:
        return NodeResult(
            update={"review_rounds": append_to_current_round(state)},
            output_summary="no claims recorded yet -- nothing to audit",
        )

    verified_keys = set(state.bib_keys)
    claims_block = "\n".join(
        f'- id={c.id}: "{c.text}" evidence_refs={c.evidence_refs} '
        f"citation_verified={any(ref in verified_keys for ref in c.evidence_refs)}"
        for c in claims
    )
    system_prompt = build_system_prompt(
        skills=["claim-evidence-map", "claim-rigor-audit"],
        local_suffix="claims_evidence_auditor",
        context={"claims": claims_block},
    )
    audit, llm_result = call_llm_json(
        [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": "Audit every claim listed above."},
        ],
        agent_name=AGENT_NAME,
        schema=ClaimsAuditResult,
    )

    audit_by_id = {a.claim_id: a for a in audit.audits}
    updated_claims = []
    major_concerns = []
    for claim in claims:
        result = audit_by_id.get(claim.id)
        if result is None:
            continue
        if result.status != claim.status:
            updated_claims.append(claim.model_copy(update={"status": result.status}))
        if result.status == "unsupported":
            major_concerns.append(f"Unsupported claim ({claim.id}): \"{claim.text}\" — {result.rationale}")

    return NodeResult(
        update={
            "claims": updated_claims,
            "review_rounds": append_to_current_round(state, major=major_concerns),
        },
        model=llm_result.model,
        prompt_tokens=llm_result.prompt_tokens,
        completion_tokens=llm_result.completion_tokens,
        cost_usd=llm_result.cost_usd,
        output_summary=f"round {round_num}: {len(major_concerns)} unsupported claims of {len(claims)} audited",
    )
