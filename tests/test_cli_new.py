import yaml

from engine import cli
from engine.tools import workspace


def test_cmd_new_scaffolds_workspace(tmp_path, monkeypatch):
    monkeypatch.setattr(workspace, "paper_dir", lambda slug: tmp_path / slug)

    cli.main(["new", "demo", "--topic", "LLM agents for supply chain exception handling"])

    pdir = tmp_path / "demo"
    for sub in [
        "ideation",
        "experiments/src",
        "experiments/data",
        "experiments/results",
        "experiments/env",
        "manuscript/sections",
        "manuscript/figures",
        "reviews",
        "provenance",
    ]:
        assert (pdir / sub).is_dir(), sub

    assert (pdir / "provenance" / "run_log.jsonl").exists()
    assert (pdir / "manuscript" / "refs.bib").exists()

    paper_yaml = yaml.safe_load((pdir / "paper.yaml").read_text())
    assert paper_yaml["paper_id"] == "demo"
    assert paper_yaml["phase"] == "ideation"
    assert paper_yaml["topic"] == "LLM agents for supply chain exception handling"


def test_cmd_new_refuses_existing_workspace(tmp_path, monkeypatch):
    monkeypatch.setattr(workspace, "paper_dir", lambda slug: tmp_path / slug)
    (tmp_path / "demo").mkdir()

    try:
        cli.main(["new", "demo", "--topic", "x"])
        raise AssertionError("expected SystemExit")
    except SystemExit:
        pass
