import json

import yaml

from engine.agents.base import NodeResult
from engine.graphs import experiments, ideation, master


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

    import engine.tools.workspace as workspace_mod

    monkeypatch.setattr(workspace_mod, "paper_dir", lambda paper_id: tmp_path / "papers" / paper_id)

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
