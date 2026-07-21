import yaml

from engine.agents import citation_verifier, claims_evidence_auditor, flow_checker, importer
from engine.llm import LLMResult
from engine.tools.common import SearchResult


def _llm_result():
    return LLMResult(content="{}", model="fake/model", prompt_tokens=5, completion_tokens=5)


def _fake_call_llm_json(messages, *, agent_name, schema, **kwargs):
    if schema is importer.ExtractedClaims:
        return schema(claims=["The proposed method beats the baseline."]), _llm_result()
    if schema is citation_verifier.ClaimSupportCheck:
        return schema(supports_claim=True, rationale="mocked"), _llm_result()
    if schema is flow_checker.ReconstructedOutline:
        return schema(sections_found=["intro"], drift_notes=[], orphaned_sections=[]), _llm_result()
    raise AssertionError(f"unexpected schema {schema}")


def _fake_claims_audit(messages, *, agent_name, schema, **kwargs):
    audit = schema(audits=[{"claim_id": "intro-0", "status": "supported", "rationale": "mocked"}])
    return audit, _llm_result()


def test_import_backfills_state_and_catches_fake_citation(tmp_path, monkeypatch):
    # --- sample existing draft with one real-looking and one fake citation ---
    source_dir = tmp_path / "source_draft"
    source_dir.mkdir()
    (source_dir / "intro.tex").write_text(
        r"\title{Imported Paper}"
        "\n"
        r"The proposed method beats the baseline \cite{real2023arxiv,fake2099nonexistent}."
    )
    (source_dir / "refs.bib").write_text(
        "@article{real2023arxiv,\n"
        "  title = {A Real Paper About Agents},\n"
        "  author = {Real Author},\n"
        "  year = {2023},\n"
        "  eprint = {2301.00001},\n"
        "  archiveprefix = {arXiv}\n"
        "}\n"
        "@article{fake2099nonexistent,\n"
        "  title = {A Completely Fabricated Paper That Does Not Exist},\n"
        "  author = {Nobody},\n"
        "  year = {2099}\n"
        "}\n"
    )

    # --- workspace + tool isolation ---
    monkeypatch.setattr(importer, "paper_dir", lambda slug: tmp_path / "papers" / slug)
    import engine.tools.workspace as workspace_mod

    monkeypatch.setattr(workspace_mod, "paper_dir", lambda slug: tmp_path / "papers" / slug)
    monkeypatch.setattr(importer.fs_guard, "PAPERS_ROOT", tmp_path / "papers")
    monkeypatch.setattr(importer, "call_llm_json", _fake_call_llm_json)

    monkeypatch.setattr(citation_verifier, "paper_dir", lambda slug: tmp_path / "papers" / slug)
    monkeypatch.setattr(citation_verifier, "call_llm_json", _fake_call_llm_json)
    monkeypatch.setattr(
        citation_verifier.arxiv,
        "get_by_id",
        lambda aid: SearchResult(title="A Real Paper About Agents", year=2023, arxiv_id=aid, source="arxiv")
        if aid == "2301.00001"
        else None,
    )
    monkeypatch.setattr(citation_verifier.semanticscholar, "search", lambda q, limit=3: [])
    monkeypatch.setattr(citation_verifier.arxiv, "search", lambda q, limit=3: [])
    monkeypatch.setattr(citation_verifier.crossref, "get_by_doi", lambda doi: None)

    monkeypatch.setattr(claims_evidence_auditor, "call_llm_json", _fake_claims_audit)

    monkeypatch.setattr(flow_checker, "paper_dir", lambda slug: tmp_path / "papers" / slug)
    monkeypatch.setattr(flow_checker.fs_guard, "PAPERS_ROOT", tmp_path / "papers")
    monkeypatch.setattr(flow_checker, "call_llm_json", _fake_call_llm_json)

    final_state = importer.import_paper("imported-demo", source_dir=str(source_dir))

    assert final_state.phase == "review"
    assert final_state.topic == "Imported Paper"
    assert any(c.text == "The proposed method beats the baseline." for c in final_state.claims)

    pdir = tmp_path / "papers" / "imported-demo"
    paper_yaml = yaml.safe_load((pdir / "paper.yaml").read_text())
    assert paper_yaml["phase"] == "review"
    assert paper_yaml["status"] == "imported"

    report = (pdir / "manuscript" / "citation_verification_report.md").read_text()
    assert "fake2099nonexistent" in report
    assert "hallucinated" in report

    round00_report = (pdir / "reviews" / "round_00" / "citation_verification_report.md").read_text()
    assert "fake2099nonexistent" in round00_report

    final_bib = (pdir / "manuscript" / "refs.bib").read_text()
    assert "real2023arxiv" in final_bib
    assert "fake2099nonexistent" not in final_bib

    statuses = {r.bib_key: r.status for r in final_state.citation_records}
    assert statuses["fake2099nonexistent"] == "hallucinated"
    assert statuses["real2023arxiv"] == "verified"


# --- chunk_text ---


def test_chunk_text_short_input_is_one_chunk():
    assert importer.chunk_text("A short paper idea.", max_chars=4000) == ["A short paper idea."]


def test_chunk_text_splits_on_paragraph_boundaries_under_the_cap():
    paragraphs = [f"Paragraph {i}. " + ("word " * 100) for i in range(20)]  # ~700 chars each
    text = "\n\n".join(paragraphs)
    chunks = importer.chunk_text(text, max_chars=2000)

    assert len(chunks) > 1
    for chunk in chunks:
        assert len(chunk) <= 2000
    # nothing lost: every paragraph's distinctive marker survives somewhere
    for i in range(20):
        assert any(f"Paragraph {i}." in c for c in chunks)


def test_chunk_text_hard_splits_a_single_oversized_paragraph_with_no_blank_lines():
    huge_single_paragraph = "x" * 10_000  # no blank lines anywhere
    chunks = importer.chunk_text(huge_single_paragraph, max_chars=4000)

    assert len(chunks) == 3  # 4000 + 4000 + 2000
    assert all(len(c) <= 4000 for c in chunks)
    assert "".join(chunks) == huge_single_paragraph


# --- import_pasted_text ---


def _isolate_importer_modules(tmp_path, monkeypatch):
    import engine.tools.workspace as workspace_mod

    for mod in (importer, citation_verifier, flow_checker):
        monkeypatch.setattr(mod, "paper_dir", lambda slug: tmp_path / "papers" / slug)
    monkeypatch.setattr(workspace_mod, "paper_dir", lambda slug: tmp_path / "papers" / slug)
    monkeypatch.setattr(importer.fs_guard, "PAPERS_ROOT", tmp_path / "papers")
    monkeypatch.setattr(flow_checker.fs_guard, "PAPERS_ROOT", tmp_path / "papers")
    monkeypatch.setattr(importer, "call_llm_json", _fake_call_llm_json)
    monkeypatch.setattr(flow_checker, "call_llm_json", _fake_call_llm_json)
    monkeypatch.setattr(claims_evidence_auditor, "call_llm_json", _fake_claims_audit)


def test_import_pasted_text_scans_every_chunk_not_just_the_first(tmp_path, monkeypatch):
    _isolate_importer_modules(tmp_path, monkeypatch)

    seen_sections: list[str] = []

    def _tracking_call_llm_json(messages, *, agent_name, schema, **kwargs):
        if schema is importer.ExtractedClaims:
            # the section name is baked into the local-suffix prompt via build_system_prompt
            seen_sections.append(messages[0]["content"])
            return schema(claims=[f"Claim from a chunk (call #{len(seen_sections)})"]), _llm_result()
        return _fake_call_llm_json(messages, agent_name=agent_name, schema=schema, **kwargs)

    monkeypatch.setattr(importer, "call_llm_json", _tracking_call_llm_json)

    # Big enough to force multiple chunks at the default 4000-char cap.
    full_text = "\n\n".join(f"Paragraph {i} of the paper. " + ("content " * 80) for i in range(20))
    assert len(full_text) > importer.DEFAULT_CHUNK_CHARS * 2  # sanity: this really does need >1 chunk

    final_state = importer.import_pasted_text(
        "pasted-demo", title="A Pasted Paper Title", full_text=full_text, bibliography=None
    )

    assert len(seen_sections) > 1, "only one chunk was scanned -- the whole-paper-review bug is back"
    assert final_state.topic == "A Pasted Paper Title"
    assert final_state.phase == "review"
    assert len(final_state.claims) == len(seen_sections)  # one claim extracted per chunk


def test_import_pasted_text_rejects_empty_input():
    import pytest

    with pytest.raises(ValueError, match="empty"):
        importer.import_pasted_text("demo", title=None, full_text="   ", bibliography=None)
