"""Small helpers shared by the review-phase agents (adversarial_reviewer_ensemble,
claims_evidence_auditor, flow_checker, compliance_checker, revision_router). Not an
agent itself, so no AGENT_NAME/SKILL -- nothing here is a graph node.
"""

from __future__ import annotations

from engine.config import paper_dir
from engine.state import PaperState, ReviewRound


def manuscript_text(paper_id: str, *, max_chars: int = 20000) -> str:
    sections_dir = paper_dir(paper_id) / "manuscript" / "sections"
    if not sections_dir.exists():
        return ""
    parts = [f"% === {f.stem} ===\n{f.read_text()}" for f in sorted(sections_dir.glob("*.tex"))]
    return "\n\n".join(parts)[:max_chars]


def current_round_number(state: PaperState) -> int:
    rounds = state.effective_review_rounds()
    return max((r.round for r in rounds), default=1)


def get_current_round(state: PaperState) -> ReviewRound | None:
    round_num = current_round_number(state)
    return next((r for r in state.effective_review_rounds() if r.round == round_num), None)


def append_to_current_round(
    state: PaperState,
    *,
    major: list[str] | None = None,
    minor: list[str] | None = None,
    verdicts: dict | None = None,
    reviewer_reports: list[str] | None = None,
) -> list[ReviewRound]:
    """Returns a single-element ReviewRound list (for the operator.add reducer)
    that merges new concerns/verdicts into the current round, creating it if this
    is the first agent to touch it this round.
    """
    round_num = current_round_number(state)
    existing = get_current_round(state)
    if existing:
        merged = existing.model_copy(
            update={
                "major_concerns": [*existing.major_concerns, *(major or [])],
                "minor_concerns": [*existing.minor_concerns, *(minor or [])],
                "verdicts": {**existing.verdicts, **(verdicts or {})},
                "reviewer_reports": [*existing.reviewer_reports, *(reviewer_reports or [])],
            }
        )
    else:
        merged = ReviewRound(
            round=round_num,
            major_concerns=list(major or []),
            minor_concerns=list(minor or []),
            verdicts=dict(verdicts or {}),
            reviewer_reports=list(reviewer_reports or []),
        )
    return [merged]
