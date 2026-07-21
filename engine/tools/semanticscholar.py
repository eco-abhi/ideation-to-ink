from __future__ import annotations

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from engine.config import SEMANTIC_SCHOLAR_API_KEY
from engine.tools.cache import cached_get
from engine.tools.common import SearchResult

SEARCH_URL = "https://api.semanticscholar.org/graph/v1/paper/search"
FIELDS = "title,abstract,year,venue,externalIds,citationCount,authors"


def _headers() -> dict[str, str]:
    return {"x-api-key": SEMANTIC_SCHOLAR_API_KEY} if SEMANTIC_SCHOLAR_API_KEY else {}


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=8),
    retry=retry_if_exception_type(httpx.HTTPError),
    reraise=True,
)
def _fetch(query: str, limit: int) -> list[dict]:
    resp = httpx.get(
        SEARCH_URL,
        params={"query": query, "limit": limit, "fields": FIELDS},
        headers=_headers(),
        timeout=20,
    )
    resp.raise_for_status()
    return resp.json().get("data", [])


def _to_result(paper: dict) -> SearchResult:
    ext = paper.get("externalIds") or {}
    return SearchResult(
        title=(paper.get("title") or "").strip(),
        abstract=paper.get("abstract"),
        year=paper.get("year"),
        venue=paper.get("venue") or None,
        doi=ext.get("DOI"),
        arxiv_id=ext.get("ArXiv"),
        citation_count=paper.get("citationCount"),
        authors=[a.get("name") for a in paper.get("authors", []) if a.get("name")],
        source="semanticscholar",
    )


def search(query: str, limit: int = 25) -> list[SearchResult]:
    raw = cached_get(
        "semanticscholar", "paper/search", {"query": query, "limit": limit}, lambda: _fetch(query, limit)
    )
    return [_to_result(p) for p in raw if (p.get("title") or "").strip()]
