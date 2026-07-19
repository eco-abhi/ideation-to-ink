import bibtexparser

from engine.agents import citation_verifier
from engine.llm import LLMResult
from engine.state import Claim, PaperState
from engine.tools.common import SearchResult

DRAFT_BIB = r"""
@article{real2023arxiv,
  title = {A Real Paper About Agents},
  author = {Real Author},
  year = {2023},
  eprint = {2301.00001},
  archiveprefix = {arXiv}
}
@article{real2022doi,
  title = {A Real DOI Paper},
  author = {DOI Author},
  year = {2022},
  doi = {10.1/real}
}
@article{fake2099hallucinated,
  title = {A Completely Made Up Paper That Does Not Exist Anywhere},
  author = {Nobody},
  year = {2099}
}
@article{mismatch2023claim,
  title = {A Real Paper With Unrelated Abstract},
  author = {Some Author},
  year = {2023},
  doi = {10.1/mismatch}
}
"""


def _setup_workspace(tmp_path, monkeypatch):
    monkeypatch.setattr(citation_verifier, "paper_dir", lambda slug: tmp_path / slug)
    monkeypatch.setattr(citation_verifier.fs_guard, "PAPERS_ROOT", tmp_path)
    pdir = tmp_path / "demo"
    (pdir / "manuscript" / "sections").mkdir(parents=True)
    (pdir / "manuscript" / "refs_draft.bib").write_text(DRAFT_BIB)
    (pdir / "manuscript" / "sections" / "intro.tex").write_text(
        "Intro text \\cite{real2023arxiv,fake2099hallucinated} and more \\cite{fake2099hallucinated}."
    )
    return pdir


def test_citation_verifier_classifies_and_gates(tmp_path, monkeypatch):
    pdir = _setup_workspace(tmp_path, monkeypatch)

    monkeypatch.setattr(
        citation_verifier.arxiv, "get_by_id",
        lambda aid: SearchResult(title="A Real Paper About Agents", year=2023, arxiv_id=aid, abstract=None, source="arxiv")
        if aid == "2301.00001" else None,
    )

    def fake_get_by_doi(doi):
        if doi == "10.1/real":
            return SearchResult(title="A Real DOI Paper", year=2022, doi=doi, abstract="Supports the claim well.", source="crossref")
        if doi == "10.1/mismatch":
            return SearchResult(title="A Real Paper With Unrelated Abstract", year=2023, doi=doi, abstract="Totally unrelated content.", source="crossref")
        return None

    monkeypatch.setattr(citation_verifier.crossref, "get_by_doi", fake_get_by_doi)
    monkeypatch.setattr(citation_verifier.semanticscholar, "search", lambda q, limit=3: [])
    monkeypatch.setattr(citation_verifier.arxiv, "search", lambda q, limit=3: [])

    def fake_call_llm_json(messages, *, agent_name, schema, **kwargs):
        claim_text = messages[-1]["content"]
        supports = "unrelated" not in claim_text.lower() and "mismatch" not in claim_text.lower()
        check = schema(supports_claim=supports, rationale="mocked")
        return check, LLMResult(content="{}", model="fake/model", prompt_tokens=5, completion_tokens=5)

    monkeypatch.setattr(citation_verifier, "call_llm_json", fake_call_llm_json)

    state = PaperState(
        paper_id="demo",
        topic="x",
        claims=[
            Claim(id="c1", text="Claim needing the mismatched DOI paper.", evidence_refs=["mismatch2023claim"]),
            Claim(id="c2", text="Claim resting entirely on the hallucinated paper.", evidence_refs=["fake2099hallucinated"]),
        ],
    )
    result = citation_verifier.citation_verifier(state)

    statuses = {r.bib_key: r.status for r in result.update["citation_records"]}
    assert statuses["real2023arxiv"] == "verified"
    assert statuses["real2022doi"] == "verified"
    assert statuses["fake2099hallucinated"] == "hallucinated"
    assert statuses["mismatch2023claim"] == "suspicious"  # verified source, but abstract doesn't support the claim

    assert set(result.update["bib_keys"]) == {"real2023arxiv", "real2022doi"}

    final_bib = (pdir / "manuscript" / "refs.bib").read_text()
    db = bibtexparser.loads(final_bib)
    assert {e["ID"] for e in db.entries} == {"real2023arxiv", "real2022doi"}

    # hallucinated citation stripped from the section that cited it
    intro_text = (pdir / "manuscript" / "sections" / "intro.tex").read_text()
    assert "fake2099hallucinated" not in intro_text
    assert "real2023arxiv" in intro_text

    # claim entirely resting on the hallucinated citation is marked disputed
    disputed = [c for c in result.update["claims"] if c.id == "c2"]
    assert disputed and disputed[0].status == "disputed"

    report = (pdir / "manuscript" / "citation_verification_report.md").read_text()
    assert "hallucinated" in report
