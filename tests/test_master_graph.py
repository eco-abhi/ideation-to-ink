import json

import yaml

from engine.agents.base import NodeResult
from engine.graphs import experiments, ideation, master, review, writing


def test_build_master_graph_compiles():
    builder = master.build_master_graph()
    builder.compile()  # raises if any wired edge target isn't a registered node


def _fake_literature_scout(state):
    return NodeResult(update={"corpus_path": "/fake/corpus.parquet"})


def _fake_novelty_checker(state):
    return NodeResult(update={"novelty_verdict": {"verdict": "PROCEED", "score": 0.1, "rationale": "distinct"}})


def _fake_rq_refiner(state):
    return NodeResult(update={"research_questions": ["q1"]})


def _fake_venue_strategist(state):
    return NodeResult(update={"venue": "neurips-style"})


def _fake_methodology_designer(state):
    return NodeResult(update={"artifacts": {**state.artifacts, "design": "experiments/DESIGN.md"}})


def _setup(tmp_path, monkeypatch, slug="demo"):
    monkeypatch.setattr(ideation, "literature_scout", _fake_literature_scout)
    monkeypatch.setattr(ideation, "novelty_checker", _fake_novelty_checker)
    monkeypatch.setattr(ideation, "rq_refiner", _fake_rq_refiner)
    monkeypatch.setattr(ideation, "venue_strategist", _fake_venue_strategist)
    monkeypatch.setattr(experiments, "methodology_designer", _fake_methodology_designer)

    monkeypatch.setattr(master, "checkpoint_path", lambda paper_id: tmp_path / f"{paper_id}.sqlite")
    monkeypatch.setattr(master, "paper_dir", lambda paper_id: tmp_path / "papers" / paper_id)

    import engine.config as config_mod
    import engine.tools.workspace as workspace_mod
    from engine.tools import fs_guard

    monkeypatch.setattr(workspace_mod, "paper_dir", lambda paper_id: tmp_path / "papers" / paper_id)
    # engine.config.PAPERS_ROOT is what the real paper_dir() function (used directly
    # by unmocked plumbing nodes like writing._mark_writing_complete) resolves against,
    # regardless of which module imported the function -- a function's globals are its
    # *defining* module's namespace, not the caller's. Patching it here, plus
    # fs_guard.PAPERS_ROOT below, isolates every real filesystem write this test doesn't
    # explicitly mock, not just the agent functions it fakes out.
    monkeypatch.setattr(config_mod, "PAPERS_ROOT", tmp_path / "papers")
    monkeypatch.setattr(fs_guard, "PAPERS_ROOT", tmp_path / "papers")

    pdir = tmp_path / "papers" / slug
    pdir.mkdir(parents=True)
    (pdir / "paper.yaml").write_text(
        yaml.safe_dump({"paper_id": slug, "topic": "x", "venue": None, "phase": "ideation", "status": "new"})
    )
    return pdir


def test_run_paper_pauses_at_first_interrupt_and_writes_human_input_file(tmp_path, monkeypatch, capsys):
    pdir = _setup(tmp_path, monkeypatch)

    master.run_paper("demo", resume=False)

    payload = json.loads((pdir / "HUMAN_INPUT_NEEDED.json").read_text())
    assert payload["type"] == "novelty_verdict"

    # calling run again without --resume just reports pending work, doesn't error or re-invoke
    master.run_paper("demo", resume=False)
    captured = capsys.readouterr()
    assert "pending work" in captured.out


def test_run_paper_resume_without_response_file_exits(tmp_path, monkeypatch):
    import pytest

    _setup(tmp_path, monkeypatch)
    master.run_paper("demo", resume=False)  # reach the interrupt

    with pytest.raises(SystemExit, match="HUMAN_RESPONSE.json"):
        master.run_paper("demo", resume=True)


def test_run_paper_resume_advances_across_phase_boundary(tmp_path, monkeypatch):
    pdir = _setup(tmp_path, monkeypatch)
    master.run_paper("demo", resume=False)  # reach novelty_verdict interrupt

    (pdir / "HUMAN_RESPONSE.json").write_text(json.dumps({"decision": "proceed"}))
    master.run_paper("demo", resume=True)

    # ideation -> experiments boundary crossed automatically; next stop is the
    # experiments phase's own human gate (methodology_approval), proving the
    # cross-phase edge (ideation.IDEATION_COMPLETE -> experiments.ENTRY_NODE) fired.
    payload = json.loads((pdir / "HUMAN_INPUT_NEEDED.json").read_text())
    assert payload["type"] == "methodology_approval"
    assert not (pdir / "HUMAN_RESPONSE.json").exists()  # consumed


def test_run_single_agent_hydrates_from_paper_yaml_when_no_checkpoint(tmp_path, monkeypatch, capsys):
    _setup(tmp_path, monkeypatch)

    def fake_citation_verifier(state):
        assert state.topic == "x"
        return NodeResult(update={}, artifacts_written=["manuscript/refs.bib"], output_summary="0 verified")

    monkeypatch.setattr(master, "CHECK_AGENTS", {**master.CHECK_AGENTS, "citation_verifier": fake_citation_verifier})

    master.run_single_agent("demo", agent_name="citation_verifier")
    captured = capsys.readouterr()
    assert "0 verified" in captured.out


def test_full_pipeline_reaches_done_and_writes_ledger(tmp_path, monkeypatch, capsys):
    """End-to-end: every phase mocked to return a clean result, two human gates
    (novelty verdict, methodology approval) resumed, results_gate passed through
    silently (metrics.json pre-seeded), citation_human_gate passed through
    silently (no suspicious citations), revision_router converging immediately
    (no major concerns) -> phase=done -> automatic state_compaction ledger write.
    """
    pdir = _setup(tmp_path, monkeypatch)

    monkeypatch.setattr(experiments, "experiment_scaffolder", lambda state: NodeResult(update={}))
    monkeypatch.setattr(experiments, "stats_validator", lambda state: NodeResult(update={}))
    monkeypatch.setattr(experiments, "paper_dir", lambda paper_id: tmp_path / "papers" / paper_id)
    (pdir / "experiments" / "results").mkdir(parents=True)
    (pdir / "experiments" / "results" / "metrics.json").write_text("{}")

    monkeypatch.setattr(writing, "structure_agent", lambda state: NodeResult(update={"outline": {"sections": []}}))
    monkeypatch.setattr(writing, "section_drafters", lambda state: NodeResult(update={}))
    monkeypatch.setattr(
        writing,
        "citation_verifier",
        lambda state: NodeResult(update={"bib_keys": [], "citation_records": []}),
    )

    monkeypatch.setattr(review, "adversarial_reviewer_ensemble", lambda state: NodeResult(update={}))
    monkeypatch.setattr(review, "claims_evidence_auditor", lambda state: NodeResult(update={}))
    monkeypatch.setattr(review, "flow_checker", lambda state: NodeResult(update={}))
    monkeypatch.setattr(review, "compliance_checker", lambda state: NodeResult(update={}))

    def fake_revision_router(state):
        from engine.state import ReviewRound

        return NodeResult(update={"review_rounds": [ReviewRound(round=1, resolved=True)], "phase": "done"})

    monkeypatch.setattr(review, "revision_router", fake_revision_router)

    ledger_calls = []
    monkeypatch.setattr(
        master,
        "state_compaction",
        lambda state: ledger_calls.append(state.paper_id) or NodeResult(update={}, output_summary="ledger ok"),
    )

    master.run_paper("demo", resume=False)  # -> novelty_verdict interrupt
    (pdir / "HUMAN_RESPONSE.json").write_text(json.dumps({"decision": "proceed"}))
    master.run_paper("demo", resume=True)  # -> methodology_approval interrupt

    payload = json.loads((pdir / "HUMAN_INPUT_NEEDED.json").read_text())
    assert payload["type"] == "methodology_approval"

    (pdir / "HUMAN_RESPONSE.json").write_text(json.dumps({"decision": "approve"}))
    master.run_paper("demo", resume=True)  # -> runs the rest of the pipeline to completion

    captured = capsys.readouterr()
    assert "phase=done" in captured.out
    assert not (pdir / "HUMAN_INPUT_NEEDED.json").exists()
    assert ledger_calls == ["demo"]

    paper_yaml = yaml.safe_load((pdir / "paper.yaml").read_text())
    assert paper_yaml["phase"] == "done"
    assert paper_yaml["status"] == "done"
