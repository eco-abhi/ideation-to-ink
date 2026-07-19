"""Shared normalized result type every literature API client returns."""

from __future__ import annotations

from pydantic import BaseModel, Field


class SearchResult(BaseModel):
    title: str
    abstract: str | None = None
    year: int | None = None
    venue: str | None = None
    doi: str | None = None
    arxiv_id: str | None = None
    citation_count: int | None = None
    authors: list[str] = Field(default_factory=list)
    source: str
