import json
import threading
import time

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
    app_module._running.clear()  # module-level set persists across tests otherwise
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


# --- write endpoints ---


def test_create_paper_scaffolds_workspace(tmp_path, client):
    response = client.post("/api/papers", json={"slug": "new-paper", "topic": "A real topic"})
    assert response.status_code == 201
    data = response.json()
    assert data["paper_id"] == "new-paper"
    assert data["phase"] == "ideation"
    assert (tmp_path / "new-paper" / "paper.yaml").exists()


def test_create_paper_rejects_bad_slug(client):
    response = client.post("/api/papers", json={"slug": "../escape", "topic": "x"})
    assert response.status_code == 400


def test_create_paper_rejects_empty_topic(client):
    response = client.post("/api/papers", json={"slug": "demo", "topic": "   "})
    assert response.status_code == 400


def test_create_paper_conflicts_on_existing_slug(tmp_path, client):
    _scaffold(tmp_path, "demo")
    response = client.post("/api/papers", json={"slug": "demo", "topic": "x"})
    assert response.status_code == 409


def _mock_run_paper(monkeypatch, *, started: threading.Event, finished: threading.Event, calls: list):
    def fake_run_paper(paper_id, *, target_phase=None, resume=False):
        calls.append({"paper_id": paper_id, "target_phase": target_phase, "resume": resume})
        started.set()
        finished.wait(timeout=5)

    monkeypatch.setattr("engine.graphs.master.run_paper", fake_run_paper)


def _wait_until_not_running(paper_id: str, timeout: float = 2.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        with app_module._running_lock:
            if paper_id not in app_module._running:
                return
        time.sleep(0.02)
    raise AssertionError(f"{paper_id} still marked running after {timeout}s")


def test_trigger_run_executes_in_background_and_reports_running(tmp_path, client, monkeypatch):
    _scaffold(tmp_path, "demo")
    started, finished, calls = threading.Event(), threading.Event(), []
    _mock_run_paper(monkeypatch, started=started, finished=finished, calls=calls)

    response = client.post("/api/papers/demo/run")
    assert response.status_code == 202
    assert started.wait(timeout=2)

    detail = client.get("/api/papers/demo").json()
    assert detail["running"] is True

    finished.set()
    _wait_until_not_running("demo")
    assert calls == [{"paper_id": "demo", "target_phase": None, "resume": False}]


def test_trigger_run_with_explicit_phase_forces_reentry(tmp_path, client, monkeypatch):
    # This is the "rerun from phase X" UI control's actual mechanism.
    _scaffold(tmp_path, "demo", phase="done", status="done")
    started, finished, calls = threading.Event(), threading.Event(), []
    _mock_run_paper(monkeypatch, started=started, finished=finished, calls=calls)

    response = client.post("/api/papers/demo/run", json={"phase": "writing"})
    assert response.status_code == 202
    assert started.wait(timeout=2)

    finished.set()
    _wait_until_not_running("demo")
    assert calls == [{"paper_id": "demo", "target_phase": "writing", "resume": False}]


def test_trigger_run_rejects_concurrent_run(tmp_path, client, monkeypatch):
    _scaffold(tmp_path, "demo")
    started, finished, calls = threading.Event(), threading.Event(), []
    _mock_run_paper(monkeypatch, started=started, finished=finished, calls=calls)

    first = client.post("/api/papers/demo/run")
    assert first.status_code == 202
    assert started.wait(timeout=2)

    second = client.post("/api/papers/demo/run")
    assert second.status_code == 409

    finished.set()
    _wait_until_not_running("demo")


def test_respond_to_gate_writes_response_file_and_resumes(tmp_path, client, monkeypatch):
    pdir = _scaffold(tmp_path, "demo")
    started, finished, calls = threading.Event(), threading.Event(), []
    _mock_run_paper(monkeypatch, started=started, finished=finished, calls=calls)

    response = client.post("/api/papers/demo/respond", json={"decision": "proceed"})
    assert response.status_code == 202
    assert started.wait(timeout=2)

    assert json.loads((pdir / "HUMAN_RESPONSE.json").read_text()) == {"decision": "proceed"}
    assert calls == [{"paper_id": "demo", "target_phase": None, "resume": True}]

    finished.set()
    _wait_until_not_running("demo")


def test_respond_to_gate_rejects_empty_body(tmp_path, client):
    _scaffold(tmp_path, "demo")
    response = client.post("/api/papers/demo/respond", json={})
    assert response.status_code == 400
