from engine.provenance import (
    ProvenanceEntry,
    format_usage_table,
    hash_input,
    log_provenance,
    summarize_usage,
    total_usage,
)


def _entry(agent, model, prompt, completion, cost, paper_id="demo"):
    return ProvenanceEntry(
        paper_id=paper_id,
        agent=agent,
        model=model,
        input_hash=hash_input({}),
        output_summary="",
        tokens={"prompt": prompt, "completion": completion},
        cost_usd=cost,
        duration_ms=1,
    )


def test_summarize_usage_aggregates_per_agent_and_skips_non_llm_nodes():
    entries = [
        _entry("literature_scout", "anthropic/claude-sonnet-5", 100, 20, 0.01),
        _entry("literature_scout", "anthropic/claude-sonnet-5", 50, 10, 0.005),
        _entry("experiment_scaffolder", None, 0, 0, None),  # deterministic node, no LLM call
        _entry("novelty_checker", "anthropic/claude-sonnet-5", 200, 40, 0.02),
    ]
    rows = summarize_usage(entries)
    by_key = {r.key: r for r in rows}

    assert "experiment_scaffolder" not in by_key
    assert by_key["literature_scout"].calls == 2
    assert by_key["literature_scout"].prompt_tokens == 150
    assert by_key["literature_scout"].completion_tokens == 30
    assert abs(by_key["literature_scout"].cost_usd - 0.015) < 1e-9
    assert by_key["novelty_checker"].cost_usd == 0.02


def test_summarize_usage_tracks_unknown_cost_separately():
    entries = [
        _entry("citation_verifier", "anthropic/claude-sonnet-5", 100, 20, None),  # cost couldn't be computed
        _entry("citation_verifier", "anthropic/claude-sonnet-5", 100, 20, 0.01),
    ]
    rows = summarize_usage(entries)
    row = rows[0]
    assert row.calls == 2
    assert row.cost_unknown_calls == 1
    assert abs(row.cost_usd - 0.01) < 1e-9  # only the known-cost call counted


def test_by_model_grouping_splits_same_agent_across_models():
    entries = [
        _entry("section_drafters", "anthropic/claude-sonnet-5", 100, 20, 0.01),
        _entry("section_drafters", "anthropic/claude-haiku-4-5", 100, 20, 0.001),
    ]
    rows_by_agent = summarize_usage(entries, by_model=False)
    rows_by_model = summarize_usage(entries, by_model=True)
    assert len(rows_by_agent) == 1
    assert len(rows_by_model) == 2


def test_total_usage_sums_all_rows():
    entries = [
        _entry("a", "m", 10, 5, 0.1),
        _entry("b", "m", 20, 5, 0.2),
    ]
    total = total_usage(entries)
    assert total.calls == 2
    assert total.prompt_tokens == 30
    assert abs(total.cost_usd - 0.3) < 1e-9


def test_format_usage_table_reports_no_usage(tmp_path, monkeypatch):
    import engine.provenance as prov

    monkeypatch.setattr(prov, "paper_dir", lambda paper_id: tmp_path / paper_id)
    assert "No LLM usage recorded" in format_usage_table("empty-paper")


def test_format_usage_table_renders_totals_and_unknown_cost_note(tmp_path, monkeypatch):
    import engine.provenance as prov

    monkeypatch.setattr(prov, "paper_dir", lambda paper_id: tmp_path / paper_id)
    log_provenance(_entry("literature_scout", "anthropic/claude-sonnet-5", 100, 20, None, paper_id="demo"))
    log_provenance(_entry("novelty_checker", "anthropic/claude-sonnet-5", 50, 10, 0.02, paper_id="demo"))

    table = format_usage_table("demo")
    assert "TOTAL" in table
    assert "literature_scout" in table
    assert "novelty_checker" in table
    assert "unknown cost" in table
