"""Phase 3 agent 3: THE hard citation gate. Only this agent may write manuscript/refs.bib
(enforced in fs_guard.ARTIFACT_WRITE_POLICY, not just by convention).

Cascade per the citation-verification-gate skill:
  L1 arXiv ID -> L2 CrossRef DOI -> L3 title search (Semantic Scholar + arXiv)
Every entry is classified verified/suspicious/hallucinated/skipped. Verified entries
then get one more LLM pass checking the matched abstract actually supports the claim
the section attached to it. Only verified entries land in refs.bib; hallucinated and
skipped entries have their \\cite{} occurrences stripped from every section .tex file
so a citation-shaped hole doesn't silently ship as a real reference.
"""

from __future__ import annotations

import re
from difflib import SequenceMatcher

import bibtexparser
from bibtexparser.bibdatabase import BibDatabase
from bibtexparser.bwriter import BibTexWriter
from pydantic import BaseModel

from engine.agents.base import NodeResult
from engine.config import paper_dir
from engine.llm import call_llm_json
from engine.prompts.loader import skill_ref
from engine.state import CitationRecord, PaperState
from engine.tools import arxiv, crossref, fs_guard, semanticscholar
from engine.tools.common import SearchResult

AGENT_NAME = "citation_verifier"
SKILL = skill_ref("citation-verification-gate")

DRAFT_BIB_RELPATH = "manuscript/refs_draft.bib"
FINAL_BIB_RELPATH = "manuscript/refs.bib"
REPORT_RELPATH = "manuscript/citation_verification_report.md"

VERIFIED_THRESHOLD = 0.85
SUSPICIOUS_THRESHOLD = 0.60


class ClaimSupportCheck(BaseModel):
    supports_claim: bool
    rationale: str


def _title_ratio(a: str, b: str) -> float:
    return SequenceMatcher(None, a.lower().strip(), b.lower().strip()).ratio()


def _best_match(title: str, candidates: list[SearchResult]) -> tuple[SearchResult | None, float]:
    best, best_ratio = None, 0.0
    for cand in candidates:
        ratio = _title_ratio(title, cand.title)
        if ratio > best_ratio:
            best, best_ratio = cand, ratio
    return best, best_ratio


def _classify(entry: dict) -> tuple[CitationRecord, SearchResult | None]:
    key = entry.get("ID", "")
    title = (entry.get("title") or "").strip("{}").strip()
    doi = entry.get("doi")
    arxiv_id = entry.get("eprint") if (entry.get("archiveprefix") or "").lower() == "arxiv" else None

    if arxiv_id:
        found = arxiv.get_by_id(arxiv_id)
        if found:
            ratio = _title_ratio(title, found.title)
            if ratio >= VERIFIED_THRESHOLD:
                return (
                    CitationRecord(
                        bib_key=key, status="verified", matched_arxiv_id=arxiv_id,
                        rationale=f"arXiv ID resolved, title ratio {ratio:.2f}",
                    ),
                    found,
                )
            if ratio >= SUSPICIOUS_THRESHOLD:
                return (
                    CitationRecord(
                        bib_key=key, status="suspicious", matched_arxiv_id=arxiv_id,
                        rationale=f"arXiv ID resolves but title ratio only {ratio:.2f}",
                    ),
                    found,
                )

    if doi:
        found = crossref.get_by_doi(doi)
        if found:
            ratio = _title_ratio(title, found.title)
            if ratio >= VERIFIED_THRESHOLD:
                return (
                    CitationRecord(
                        bib_key=key, status="verified", matched_doi=doi,
                        rationale=f"DOI resolved, title ratio {ratio:.2f}",
                    ),
                    found,
                )
            return (
                CitationRecord(
                    bib_key=key, status="suspicious", matched_doi=doi,
                    rationale=f"DOI resolves but title ratio only {ratio:.2f}",
                ),
                found,
            )

    if not title:
        return CitationRecord(bib_key=key, status="skipped", rationale="no usable title/DOI/arXiv id"), None

    candidates: list[SearchResult] = []
    for search_fn in (semanticscholar.search, arxiv.search):
        try:
            candidates.extend(search_fn(title, limit=3))
        except Exception:  # noqa: BLE001 -- a flaky lookup source should not fail the whole gate
            continue
    best, ratio = _best_match(title, candidates)
    if best and ratio >= VERIFIED_THRESHOLD:
        return (
            CitationRecord(
                bib_key=key, status="verified", matched_doi=best.doi, matched_arxiv_id=best.arxiv_id,
                rationale=f"title search match, ratio {ratio:.2f}",
            ),
            best,
        )
    if best and ratio >= SUSPICIOUS_THRESHOLD:
        return (
            CitationRecord(
                bib_key=key, status="suspicious", matched_doi=best.doi, matched_arxiv_id=best.arxiv_id,
                rationale=f"weak title search match, ratio {ratio:.2f}",
            ),
            best,
        )
    return CitationRecord(bib_key=key, status="hallucinated", rationale="no credible match via arXiv/DOI/title search"), None


def _claim_texts_for_key(state: PaperState, key: str) -> list[str]:
    return [c.text for c in state.claims if key in c.evidence_refs]


def _strip_citation_from_sections(paper_id: str, keys_to_strip: set[str]) -> list[str]:
    if not keys_to_strip:
        return []
    sections_dir = paper_dir(paper_id) / "manuscript" / "sections"
    if not sections_dir.exists():
        return []
    touched = []
    pattern = re.compile(r"\\cite\{([^}]*)\}")

    def _clean(match: re.Match) -> str:
        remaining = [k for k in match.group(1).split(",") if k.strip() not in keys_to_strip]
        return "\\cite{" + ",".join(remaining) + "}" if remaining else ""

    for tex_file in sections_dir.glob("*.tex"):
        original = tex_file.read_text()
        cleaned = pattern.sub(_clean, original)
        if cleaned != original:
            relpath = f"manuscript/sections/{tex_file.name}"
            fs_guard.safe_write(paper_id, relpath, cleaned, caller_agent=AGENT_NAME)
            touched.append(relpath)
    return touched


def citation_verifier(state: PaperState) -> NodeResult:
    draft_path = paper_dir(state.paper_id) / DRAFT_BIB_RELPATH
    if not draft_path.exists():
        raise ValueError(f"{DRAFT_BIB_RELPATH} not found (run section_drafters first)")

    db = bibtexparser.loads(draft_path.read_text())
    records: list[CitationRecord] = []
    verified_entries: list[dict] = []
    total_prompt_tokens = total_completion_tokens = 0
    total_cost_usd = 0.0
    model_used: str | None = None

    for entry in db.entries:
        record, matched = _classify(entry)

        if record.status == "verified" and matched and matched.abstract:
            for claim_text in _claim_texts_for_key(state, record.bib_key):
                check, llm_result = call_llm_json(
                    [
                        {
                            "role": "system",
                            "content": (
                                "You verify whether a source's abstract actually supports a claim "
                                "a paper attaches to it. Be skeptical of superficial keyword overlap."
                            ),
                        },
                        {
                            "role": "user",
                            "content": f"Claim: {claim_text}\n\nAbstract: {matched.abstract}",
                        },
                    ],
                    agent_name=AGENT_NAME,
                    schema=ClaimSupportCheck,
                )
                total_prompt_tokens += llm_result.prompt_tokens
                total_completion_tokens += llm_result.completion_tokens
                total_cost_usd += llm_result.cost_usd or 0.0
                model_used = llm_result.model
                if not check.supports_claim:
                    record = CitationRecord(
                        bib_key=record.bib_key,
                        status="suspicious",
                        matched_doi=record.matched_doi,
                        matched_arxiv_id=record.matched_arxiv_id,
                        rationale=f"source found but does not support the attached claim: {check.rationale}",
                    )
                    break

        records.append(record)
        if record.status == "verified":
            verified_entries.append(entry)

    final_db = BibDatabase()
    final_db.entries = verified_entries
    fs_guard.safe_write(
        state.paper_id, FINAL_BIB_RELPATH, BibTexWriter().write(final_db), caller_agent=AGENT_NAME
    )

    keys_to_strip = {r.bib_key for r in records if r.status in ("hallucinated", "skipped")}
    stripped_sections = _strip_citation_from_sections(state.paper_id, keys_to_strip)

    updated_claims = []
    for claim in state.claims:
        bad_refs = [ref for ref in claim.evidence_refs if ref in keys_to_strip]
        if bad_refs and set(claim.evidence_refs) <= keys_to_strip:
            updated_claims.append(claim.model_copy(update={"status": "disputed"}))

    counts = {status: sum(1 for r in records if r.status == status) for status in
              ("verified", "suspicious", "hallucinated", "skipped")}
    report_lines = [
        "# Citation Verification Report",
        "",
        f"Total: {len(records)} | " + " | ".join(f"{k}: {v}" for k, v in counts.items()),
        "",
    ]
    for r in records:
        report_lines.append(f"- `{r.bib_key}` — **{r.status}** — {r.rationale}")
    fs_guard.safe_write(state.paper_id, REPORT_RELPATH, "\n".join(report_lines), caller_agent=AGENT_NAME)

    return NodeResult(
        update={
            "bib_keys": [e["ID"] for e in verified_entries],
            "citation_records": records,
            "claims": updated_claims,
            "artifacts": {
                **state.artifacts,
                "refs_bib": FINAL_BIB_RELPATH,
                "citation_report": REPORT_RELPATH,
            },
        },
        model=model_used,
        prompt_tokens=total_prompt_tokens,
        completion_tokens=total_completion_tokens,
        cost_usd=total_cost_usd,
        artifacts_written=[FINAL_BIB_RELPATH, REPORT_RELPATH, *stripped_sections],
        output_summary=" | ".join(f"{k}={v}" for k, v in counts.items()),
    )
