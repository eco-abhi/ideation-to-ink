import json

from web.backend import flow_status


def _write_provenance(tmp_path, paper_id, entries):
    log_path = tmp_path / paper_id / "provenance" / "run_log.jsonl"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("w") as f:
        for agent, error in entries:
            f.write(
                json.dumps(
                    {
                        "ts": "2026-01-01T00:00:00Z",
                        "paper_id": paper_id,
                        "agent": agent,
                        "model": None,
                        "skill_name": None,
                        "skill_upstream_commit": None,
                        "input_hash": "x",
                        "output_summary": "",
                        "tokens": {},
                        "cost_usd": None,
                        "artifacts_written": [],
                        "duration_ms": 1,
                        "error": error,
                    }
                )
                + "\n"
            )


def test_pending_pipeline_before_any_run(tmp_path, monkeypatch):
    monkeypatch.setattr(flow_status, "paper_dir", lambda paper_id: tmp_path / paper_id)
    (tmp_path / "demo").mkdir()

    result = flow_status.compute_flow_status("demo")
    statuses = {n.id: n.status for n in result.node_status}
    assert statuses["literature_scout"] == "pending"
    assert result.paused_gate is None


def test_completed_agents_mark_gates_as_silently_passed(tmp_path, monkeypatch):
    monkeypatch.setattr(flow_status, "paper_dir", lambda paper_id: tmp_path / paper_id)
    _write_provenance(
        tmp_path, "demo", [("literature_scout", None), ("novelty_checker", None), ("rq_refiner", None)]
    )

    result = flow_status.compute_flow_status("demo")
    statuses = {n.id: n.status for n in result.node_status}
    assert statuses["literature_scout"] == "completed"
    assert statuses["novelty_checker"] == "completed"
    # novelty_human_gate is never traced/logged, but rq_refiner (later in pipeline
    # order) completed, so the gate must have been passed through
    assert statuses["novelty_human_gate"] == "completed"
    assert statuses["rq_refiner"] == "completed"
    assert statuses["venue_strategist"] == "pending"  # not reached yet


def test_paused_gate_overrides_position_heuristic(tmp_path, monkeypatch):
    monkeypatch.setattr(flow_status, "paper_dir", lambda paper_id: tmp_path / paper_id)
    _write_provenance(tmp_path, "demo", [("literature_scout", None), ("novelty_checker", None)])
    (tmp_path / "demo" / "HUMAN_INPUT_NEEDED.json").write_text(
        json.dumps({"type": "novelty_verdict", "paper_id": "demo", "verdict": "PROCEED"})
    )

    result = flow_status.compute_flow_status("demo")
    statuses = {n.id: n.status for n in result.node_status}
    assert statuses["novelty_human_gate"] == "paused"
    assert result.paused_gate == "novelty_human_gate"
    assert result.gate_payload["verdict"] == "PROCEED"


def test_failed_node_marked_failed_and_error_gate_paused(tmp_path, monkeypatch):
    monkeypatch.setattr(flow_status, "paper_dir", lambda paper_id: tmp_path / paper_id)
    _write_provenance(tmp_path, "demo", [("literature_scout", "RuntimeError: boom")])
    (tmp_path / "demo" / "HUMAN_INPUT_NEEDED.json").write_text(
        json.dumps({"type": "node_error", "paper_id": "demo", "unacknowledged_errors": ["boom"]})
    )

    result = flow_status.compute_flow_status("demo")
    statuses = {n.id: n.status for n in result.node_status}
    assert statuses["literature_scout"] == "failed"
    assert statuses["error_gate"] == "paused"
    assert result.paused_gate == "error_gate"
