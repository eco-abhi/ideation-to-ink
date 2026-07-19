"""PaperState: the single shared contract every node reads and partially updates.

Nodes never mutate state in place -- they return a dict of the fields they changed,
and LangGraph merges it in. List fields that more than one node might append to
concurrently (errors, claims, review_rounds) use an `operator.add` reducer so
partial updates accumulate instead of clobbering each other.

State stores *paths* to artifacts, never artifact content.
"""

from __future__ import annotations

import operator
from datetime import date
from typing import Annotated, Literal

from pydantic import BaseModel, Field

Phase = Literal["ideation", "experiments", "writing", "review", "revision", "done"]
ClaimStatus = Literal["unsupported", "supported", "disputed"]
CitationStatus = Literal["verified", "suspicious", "hallucinated", "skipped"]


class Claim(BaseModel):
    id: str
    text: str
    evidence_refs: list[str] = Field(default_factory=list)
    status: ClaimStatus = "unsupported"


class ReviewRound(BaseModel):
    round: int
    reviewer_reports: list[str] = Field(default_factory=list)  # artifact paths
    verdicts: dict[str, object] = Field(default_factory=dict)
    major_concerns: list[str] = Field(default_factory=list)
    minor_concerns: list[str] = Field(default_factory=list)
    resolved: bool = False


class CitationRecord(BaseModel):
    bib_key: str
    status: CitationStatus
    matched_doi: str | None = None
    matched_arxiv_id: str | None = None
    rationale: str = ""


class PaperState(BaseModel):
    paper_id: str
    phase: Phase = "ideation"

    topic: str
    venue: str | None = None
    deadline: date | None = None

    research_questions: list[str] = Field(default_factory=list)

    corpus_path: str | None = None
    novelty_verdict: dict | None = None

    outline: dict | None = None
    claims: Annotated[list[Claim], operator.add] = Field(default_factory=list)

    bib_keys: list[str] = Field(default_factory=list)
    citation_records: Annotated[list[CitationRecord], operator.add] = Field(default_factory=list)

    review_rounds: Annotated[list[ReviewRound], operator.add] = Field(default_factory=list)
    revision_loop_count: int = 0

    artifacts: dict[str, str] = Field(default_factory=dict)
    errors: Annotated[list[str], operator.add] = Field(default_factory=list)
    # errors[:errors_acknowledged_count] have already been surfaced via error_gate's
    # interrupt(); routers use len(errors) > errors_acknowledged_count to detect *new*
    # failures without re-triggering on old, already-acknowledged ones after --resume.
    errors_acknowledged_count: int = 0
