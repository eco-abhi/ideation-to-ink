from __future__ import annotations

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from engine.tools.cache import cached_get
from engine.tools.common import SearchResult

BASE_URL = "https://api.openalex.org/works"


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=8),
    retry=retry_if_exception_type(httpx.HTTPError),
)
def _fetch(query: str, limit: int) -> list[dict]:
    resp = httpx.get(BASE_URL, params={"search": query, "per_page": limit}, timeout=20)
    resp.raise_for_status()
    return resp.json().get("results", [])


def _reconstruct_abstract(inverted: dict[str, list[int]] | None) -> str | None:
    if not inverted:
        return None
    positions: dict[int, str] = {}
    for word, idxs in inverted.items():
        for i in idxs:
            positions[i] = word
    return " ".join(positions[i] for i in sorted(positions))


def _venue_name(work: dict) -> str | None:
    location = work.get("primary_location") or {}
    source = location.get("source") or work.get("host_venue") or {}
    return source.get("display_name") if isinstance(source, dict) else None


def _to_result(work: dict) -> SearchResult:
    doi = work.get("doi")
    if doi:
        doi = doi.replace("https://doi.org/", "")
    return SearchResult(
        title=(work.get("title") or "").strip(),
        abstract=_reconstruct_abstract(work.get("abstract_inverted_index")),
        year=work.get("publication_year"),
        venue=_venue_name(work),
        doi=doi,
        citation_count=work.get("cited_by_count"),
        authors=[
            a["author"]["display_name"]
            for a in work.get("authorships", [])
            if a.get("author", {}).get("display_name")
        ],
        source="openalex",
    )


def search(query: str, limit: int = 25) -> list[SearchResult]:
    raw = cached_get("openalex", "works", {"query": query, "limit": limit}, lambda: _fetch(query, limit))
    return [_to_result(w) for w in raw if (w.get("title") or "").strip()]
