import json

import pytest
import yaml
from fastapi.testclient import TestClient

from web.backend import app as app_module


@pytest.fixture
def client(tmp_path, monkeypatch):
    # app.py imports PAPERS_ROOT as a value (like fs_guard/cache do), so it needs
    # its own patch -- the autouse conftest fixture covers paper_dir()/checkpoint_path()
    # (function imports, fixed transitively) but not this direct binding.
    monkeypatch.setattr(app_module, "PAPERS_ROOT", tmp_path)
    return TestClient(app_module.app)


def _scaffold(tmp_path, slug, *, topic="Test Topic", venue=None, phase="ideation", status="new"):
    pdir = tmp_path / slug
    (pdir / "provenance").mkdir(parents=True)
    (pdir / "paper.yaml").write_text(
        yaml.safe_dump({"paper_id": slug, "topic": topic, "venue": venue, "phase": phase, "status": status})
    )
    return pdir


def test_list_papers_empty_when_no_papers_root(client):
    response = client.get("/api/papers")
    assert response.status_code == 200
    assert response.json() == []


def test_list_papers_returns_summaries(tmp_path, client):
    _scaffold(tmp_path, "demo", topic="LLM agents for supply chain exception handling")
    response = client.get("/api/papers")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["paper_id"] == "demo"
    assert data[0]["topic"] == "LLM agents for supply chain exception handling"


def test_get_paper_404_for_unknown_slug(client):
    response = client.get("/api/papers/nope")
    assert response.status_code == 404


def test_get_paper_falls_back_to_paper_yaml_with_no_checkpoint(tmp_path, client):
    _scaffold(tmp_path, "demo", phase="writing", status="in_progress")
    response = client.get("/api/papers/demo")
    assert response.status_code == 200
    data = response.json()
    assert data["phase"] == "writing"
    assert data["paused"] is False


def test_get_paper_reports_paused_gate_from_human_input_file(tmp_path, client):
    pdir = _scaffold(tmp_path, "demo", phase="ideation")
    (pdir / "HUMAN_INPUT_NEEDED.json").write_text(
        json.dumps({"type": "novelty_verdict", "paper_id": "demo", "verdict": "PROCEED"})
    )
    response = client.get("/api/papers/demo")
    data = response.json()
    assert data["paused"] is True
    assert data["gate_payload"]["type"] == "novelty_verdict"


def test_get_flow_returns_topology_and_status(tmp_path, client):
    _scaffold(tmp_path, "demo")
    response = client.get("/api/papers/demo/flow")
    assert response.status_code == 200
    data = response.json()
    assert len(data["nodes"]) > 0
    assert len(data["edges"]) > 0
    assert all(n["status"] == "pending" for n in data["node_status"])


def test_get_flow_404_for_unknown_paper(client):
    assert client.get("/api/papers/nope/flow").status_code == 404


def test_get_provenance_returns_logged_entries(tmp_path, client):
    pdir = _scaffold(tmp_path, "demo")
    entry = {
        "ts": "2026-01-01T00:00:00Z",
        "paper_id": "demo",
        "agent": "literature_scout",
        "model": "anthropic/claude-sonnet-5",
        "skill_name": "literature-search",
        "skill_upstream_commit": "abc",
        "input_hash": "x",
        "output_summary": "ok",
        "tokens": {"prompt": 100, "completion": 20},
        "cost_usd": 0.01,
        "artifacts_written": [],
        "duration_ms": 5,
        "error": None,
    }
    (pdir / "provenance" / "run_log.jsonl").write_text(json.dumps(entry) + "\n")

    response = client.get("/api/papers/demo/provenance")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["agent"] == "literature_scout"


def test_get_costs_aggregates_usage(tmp_path, client):
    pdir = _scaffold(tmp_path, "demo")
    entries = [
        {
            "ts": "2026-01-01T00:00:00Z",
            "paper_id": "demo",
            "agent": "literature_scout",
            "model": "anthropic/claude-sonnet-5",
            "skill_name": None,
            "skill_upstream_commit": None,
            "input_hash": "x",
            "output_summary": "",
            "tokens": {"prompt": 100, "completion": 20},
            "cost_usd": 0.01,
            "artifacts_written": [],
            "duration_ms": 5,
            "error": None,
        }
    ]
    with (pdir / "provenance" / "run_log.jsonl").open("w") as f:
        for e in entries:
            f.write(json.dumps(e) + "\n")

    response = client.get("/api/papers/demo/costs")
    assert response.status_code == 200
    data = response.json()
    assert data["total"]["calls"] == 1
    assert abs(data["total"]["cost_usd"] - 0.01) < 1e-9


def test_get_artifact_returns_content(tmp_path, client):
    pdir = _scaffold(tmp_path, "demo")
    (pdir / "ideation").mkdir()
    (pdir / "ideation" / "novelty_report.md").write_text("# Novelty Report\n\nPROCEED")

    response = client.get("/api/papers/demo/artifacts/ideation/novelty_report.md")
    assert response.status_code == 200
    assert "PROCEED" in response.json()["content"]


def test_get_artifact_404_for_missing_file(tmp_path, client):
    _scaffold(tmp_path, "demo")
    response = client.get("/api/papers/demo/artifacts/ideation/does_not_exist.md")
    assert response.status_code == 404


def test_get_artifact_rejects_path_traversal(tmp_path, client):
    _scaffold(tmp_path, "demo")
    response = client.get("/api/papers/demo/artifacts/../../etc/passwd")
    assert response.status_code in (400, 404)
