from __future__ import annotations

import xml.etree.ElementTree as ET

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from engine.tools.cache import cached_get
from engine.tools.common import SearchResult

BASE_URL = "http://export.arxiv.org/api/query"
ATOM_NS = "{http://www.w3.org/2005/Atom}"


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=8),
    retry=retry_if_exception_type(httpx.HTTPError),
)
def _fetch_search(query: str, limit: int) -> str:
    resp = httpx.get(
        BASE_URL, params={"search_query": f"all:{query}", "max_results": limit}, timeout=20
    )
    resp.raise_for_status()
    return resp.text


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=8),
    retry=retry_if_exception_type(httpx.HTTPError),
)
def _fetch_by_id(arxiv_id: str) -> str:
    resp = httpx.get(BASE_URL, params={"id_list": arxiv_id}, timeout=20)
    resp.raise_for_status()
    return resp.text


def _parse(xml_text: str) -> list[SearchResult]:
    root = ET.fromstring(xml_text)
    results = []
    for entry in root.findall(f"{ATOM_NS}entry"):
        title = (entry.findtext(f"{ATOM_NS}title") or "").strip().replace("\n", " ")
        if not title:
            continue
        summary = (entry.findtext(f"{ATOM_NS}summary") or "").strip() or None
        id_url = entry.findtext(f"{ATOM_NS}id") or ""
        arxiv_id = id_url.rsplit("/abs/", 1)[-1] if "/abs/" in id_url else None
        published = entry.findtext(f"{ATOM_NS}published") or ""
        year = int(published[:4]) if published[:4].isdigit() else None
        authors = [a.findtext(f"{ATOM_NS}name") for a in entry.findall(f"{ATOM_NS}author")]
        results.append(
            SearchResult(
                title=title,
                abstract=summary,
                year=year,
                venue="arXiv",
                arxiv_id=arxiv_id,
                authors=[a for a in authors if a],
                source="arxiv",
            )
        )
    return results


def search(query: str, limit: int = 25) -> list[SearchResult]:
    xml_text = cached_get("arxiv", "query", {"query": query, "limit": limit}, lambda: _fetch_search(query, limit))
    return _parse(xml_text)


def get_by_id(arxiv_id: str) -> SearchResult | None:
    xml_text = cached_get("arxiv", "id_lookup", {"id": arxiv_id}, lambda: _fetch_by_id(arxiv_id))
    results = _parse(xml_text)
    return results[0] if results else None
