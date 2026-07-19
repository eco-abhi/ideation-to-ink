from engine.agents import (
    adversarial_reviewer_ensemble,
    claims_evidence_auditor,
    compliance_checker,
    flow_checker,
)
from engine.llm import LLMResult
from engine.state import Claim, PaperState


def _llm_result(**kwargs):
    return LLMResult(content="{}", model="fake/model", prompt_tokens=10, completion_tokens=5)


def test_adversarial_reviewer_ensemble_writes_reports_and_merges_round(tmp_path, monkeypatch):
    def fake_call_llm_json(messages, *, agent_name, schema, **kwargs):
        verdict = schema(
            overall_score=4.0,
            recommendation="weak_reject",
            major_concerns=["missing baseline"],
            minor_concerns=["typo in eq 3"],
            summary="Needs work.",
        )
        return verdict, _llm_result()

    monkeypatch.setattr(adversarial_reviewer_ensemble, "call_llm_json", fake_call_llm_json)
    monkeypatch.setattr(adversarial_reviewer_ensemble, "get_venue", lambda slug: None)
    monkeypatch.setattr(adversarial_reviewer_ensemble.fs_guard, "PAPERS_ROOT", tmp_path)
    (tmp_path / "demo").mkdir()

    state = PaperState(paper_id="demo", topic="x")
    result = adversarial_reviewer_ensemble.adversarial_reviewer_ensemble(state)

    rounds = result.update["review_rounds"]
    assert len(rounds) == 1
    assert rounds[0].round == 1
    assert len(rounds[0].major_concerns) == 3  # one per default persona
    for i in range(1, 4):
        assert (tmp_path / "demo" / "reviews" / "round_01" / f"reviewer_{i}.md").exists()


def test_claims_evidence_auditor_flags_unsupported(monkeypatch):
    def fake_call_llm_json(messages, *, agent_name, schema, **kwargs):
        audit = schema(
            audits=[
                {"claim_id": "c1", "status": "supported", "rationale": "fine"},
                {"claim_id": "c2", "status": "unsupported", "rationale": "no real evidence"},
            ]
        )
        return audit, _llm_result()

    monkeypatch.setattr(claims_evidence_auditor, "call_llm_json", fake_call_llm_json)

    state = PaperState(
        paper_id="demo",
        topic="x",
        claims=[
            Claim(id="c1", text="supported claim", evidence_refs=["key1"]),
            Claim(id="c2", text="unsupported claim", evidence_refs=[], status="supported"),
        ],
        bib_keys=["key1"],
    )
    result = claims_evidence_auditor.claims_evidence_auditor(state)

    rounds = result.update["review_rounds"]
    assert len(rounds[0].major_concerns) == 1
    assert "c2" in rounds[0].major_concerns[0]
    updated = {c.id: c.status for c in result.update["claims"]}
    assert updated["c2"] == "unsupported"


def test_claims_evidence_auditor_no_claims_short_circuits(monkeypatch):
    called = []
    monkeypatch.setattr(
        claims_evidence_auditor, "call_llm_json", lambda *a, **k: called.append(1) or (_ for _ in ()).throw(AssertionError)
    )
    state = PaperState(paper_id="demo", topic="x", claims=[])
    result = claims_evidence_auditor.claims_evidence_auditor(state)
    assert called == []
    assert result.update["review_rounds"][0].major_concerns == []


def test_flow_checker_flags_missing_section(tmp_path, monkeypatch):
    def fake_call_llm_json(messages, *, agent_name, schema, **kwargs):
        recon = schema(sections_found=["introduction"], drift_notes=[], orphaned_sections=[])
        return recon, _llm_result()

    monkeypatch.setattr(flow_checker, "call_llm_json", fake_call_llm_json)
    monkeypatch.setattr(flow_checker, "paper_dir", lambda slug: tmp_path / slug)
    monkeypatch.setattr(flow_checker.fs_guard, "PAPERS_ROOT", tmp_path)

    pdir = tmp_path / "demo"
    (pdir / "manuscript" / "sections").mkdir(parents=True)
    (pdir / "manuscript" / "sections" / "introduction.tex").write_text("intro text")

    state = PaperState(paper_id="demo", topic="x", outline={"sections": ["introduction", "methods"]})
    result = flow_checker.flow_checker(state)

    rounds = result.update["review_rounds"]
    assert any("methods" in c and "missing" in c for c in rounds[0].major_concerns)


def test_compliance_checker_scores_and_flags_failures(tmp_path, monkeypatch):
    def fake_call_llm_json(messages, *, agent_name, schema, **kwargs):
        report = schema(
            items=[
                {"item": "Anonymization", "passed": True, "notes": "ok"},
                {"item": "Limitations section present", "passed": False, "notes": "missing"},
            ],
            score=0.4,
        )
        return report, _llm_result()

    monkeypatch.setattr(compliance_checker, "call_llm_json", fake_call_llm_json)
    monkeypatch.setattr(compliance_checker, "get_venue", lambda slug: None)
    monkeypatch.setattr(compliance_checker.fs_guard, "PAPERS_ROOT", tmp_path)
    (tmp_path / "demo").mkdir()

    state = PaperState(paper_id="demo", topic="x")
    result = compliance_checker.compliance_checker(state)

    rounds = result.update["review_rounds"]
    assert rounds[0].verdicts["compliance_score"] == 0.4
    assert len(rounds[0].minor_concerns) == 1
    assert (tmp_path / "demo" / "reviews" / "round_01" / "compliance_scorecard.md").exists()
