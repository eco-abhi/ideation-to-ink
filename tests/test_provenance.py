from engine.provenance import ProvenanceEntry, hash_input, log_provenance, read_provenance


def test_log_and_read_roundtrip(tmp_path, monkeypatch):
    import engine.provenance as prov

    monkeypatch.setattr(prov, "paper_dir", lambda paper_id: tmp_path / paper_id)

    entry = ProvenanceEntry(
        paper_id="demo",
        agent="literature_scout",
        model="anthropic/claude-sonnet-5",
        skill_name="literature-search",
        skill_upstream_commit="deadbeef",
        input_hash=hash_input({"topic": "x"}),
        output_summary="found 5 works",
        tokens={"prompt": 100, "completion": 20},
        artifacts_written=["ideation/corpus.parquet"],
        duration_ms=42,
    )
    log_provenance(entry)
    log_provenance(entry)

    entries = read_provenance("demo")
    assert len(entries) == 2
    assert entries[0].agent == "literature_scout"
    assert entries[0].skill_upstream_commit == "deadbeef"


def test_read_provenance_missing_paper_returns_empty(tmp_path, monkeypatch):
    import engine.provenance as prov

    monkeypatch.setattr(prov, "paper_dir", lambda paper_id: tmp_path / paper_id)
    assert read_provenance("nope") == []


def test_hash_input_is_deterministic():
    a = hash_input({"b": 2, "a": 1})
    b = hash_input({"a": 1, "b": 2})
    assert a == b
