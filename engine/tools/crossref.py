from __future__ import annotations

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from engine.config import CROSSREF_CONTACT_EMAIL
from engine.tools.cache import cached_get
from engine.tools.common import SearchResult

BASE_URL = "https://api.crossref.org/works"


def _headers() -> dict[str, str]:
    ua = "research-pipeline/0.1 (mailto:not-set@example.com)"
    if CROSSREF_CONTACT_EMAIL:
        ua = f"research-pipeline/0.1 (mailto:{CROSSREF_CONTACT_EMAIL})"
    return {"User-Agent": ua}


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=8),
    retry=retry_if_exception_type(httpx.HTTPError),
    reraise=True,
)
def _fetch_by_doi(doi: str) -> dict | None:
    resp = httpx.get(f"{BASE_URL}/{doi}", headers=_headers(), timeout=20)
    if resp.status_code == 404:
        return None
    resp.raise_for_status()
    return resp.json().get("message")


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=8),
    retry=retry_if_exception_type(httpx.HTTPError),
    reraise=True,
)
def _fetch_search(query: str, limit: int) -> list[dict]:
    resp = httpx.get(
        BASE_URL, params={"query.bibliographic": query, "rows": limit}, headers=_headers(), timeout=20
    )
    resp.raise_for_status()
    return resp.json().get("message", {}).get("items", [])


def _to_result(message: dict) -> SearchResult:
    title = (message.get("title") or [""])[0]
    authors = [
        f"{a.get('given', '')} {a.get('family', '')}".strip() for a in message.get("author", [])
    ]
    year = None
    date_info = message.get("published") or message.get("published-print") or message.get(
        "published-online"
    )
    date_parts = (date_info or {}).get("date-parts")
    if date_parts and date_parts[0]:
        year = date_parts[0][0]
    return SearchResult(
        title=title,
        year=year,
        venue=(message.get("container-title") or [None])[0],
        doi=message.get("DOI"),
        citation_count=message.get("is-referenced-by-count"),
        authors=[a for a in authors if a],
        source="crossref",
    )


def get_by_doi(doi: str) -> SearchResult | None:
    message = cached_get("crossref", f"works/{doi}", {"doi": doi}, lambda: _fetch_by_doi(doi))
    return _to_result(message) if message else None


def search(query: str, limit: int = 25) -> list[SearchResult]:
    raw = cached_get(
        "crossref", "works", {"query": query, "limit": limit}, lambda: _fetch_search(query, limit)
    )
    return [_to_result(m) for m in raw if (m.get("title") or [""])[0]]
