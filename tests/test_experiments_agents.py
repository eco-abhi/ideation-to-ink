import json

from engine.agents import experiment_scaffolder, methodology_designer, stats_validator
from engine.llm import LLMResult
from engine.state import PaperState


def test_methodology_designer_writes_design_md(tmp_path, monkeypatch):
    def fake_call_llm_json(messages, *, agent_name, schema, **kwargs):
        design = schema(
            methodology="Compare agent vs rule-based baseline.",
            baselines=["rule-based system"],
            ablations=["no tool use"],
            metrics=["mean time-to-resolution"],
            datasets=["synthetic exceptions"],
            risks=["small sample size"],
        )
        return design, LLMResult(content="{}", model="fake/model", prompt_tokens=10, completion_tokens=10)

    monkeypatch.setattr(methodology_designer, "call_llm_json", fake_call_llm_json)
    monkeypatch.setattr(methodology_designer.fs_guard, "PAPERS_ROOT", tmp_path)
    (tmp_path / "demo").mkdir()

    state = PaperState(paper_id="demo", topic="x", research_questions=["does it help?"])
    result = methodology_designer.methodology_designer(state)

    assert result.update["artifacts"]["design"] == "experiments/DESIGN.md"
    design_text = (tmp_path / "demo" / "experiments" / "DESIGN.md").read_text()
    assert "rule-based system" in design_text


def test_experiment_scaffolder_writes_skeleton(tmp_path, monkeypatch):
    monkeypatch.setattr(experiment_scaffolder.fs_guard, "PAPERS_ROOT", tmp_path)
    pdir = tmp_path / "demo"
    pdir.mkdir()
    (pdir / "experiments").mkdir()
    (pdir / "experiments" / "DESIGN.md").write_text("# Experiment Design\n\nSome design.")

    state = PaperState(paper_id="demo", topic="x")
    result = experiment_scaffolder.experiment_scaffolder(state)

    assert (pdir / "experiments" / "src" / "run_experiment.py").exists()
    assert (pdir / "experiments" / "env" / "requirements.lock").exists()
    seeds = json.loads((pdir / "experiments" / "seeds.json").read_text())
    assert seeds == [0, 1, 2]
    assert result.model is None  # deterministic, no LLM call


def test_stats_validator_requires_results_file(tmp_path, monkeypatch):
    import pytest

    monkeypatch.setattr(stats_validator, "paper_dir", lambda slug: tmp_path / slug)
    (tmp_path / "demo").mkdir()

    state = PaperState(paper_id="demo", topic="x")
    with pytest.raises(ValueError, match="metrics.json not found"):
        stats_validator.stats_validator(state)


def test_stats_validator_flags_missing_significance_and_writes_report(tmp_path, monkeypatch):
    def fake_call_llm_json(messages, *, agent_name, schema, **kwargs):
        validation = schema(
            significance_tests_present=False,
            effect_sizes_reported=True,
            numbers_traceable=True,
            issues=[],
            results_summary_md="# Results\n\nAgent beats baseline by 10%.",
        )
        return validation, LLMResult(content="{}", model="fake/model", prompt_tokens=10, completion_tokens=10)

    monkeypatch.setattr(stats_validator, "call_llm_json", fake_call_llm_json)
    monkeypatch.setattr(stats_validator, "paper_dir", lambda slug: tmp_path / slug)
    monkeypatch.setattr(stats_validator.fs_guard, "PAPERS_ROOT", tmp_path)

    pdir = tmp_path / "demo"
    (pdir / "experiments" / "results").mkdir(parents=True)
    (pdir / "experiments" / "results" / "metrics.json").write_text(json.dumps({"accuracy": 0.9}))

    state = PaperState(paper_id="demo", topic="x")
    result = stats_validator.stats_validator(state)

    assert "significance" in result.output_summary.lower()
    report_path = pdir / "experiments" / "results_report.md"
    assert report_path.exists()
    assert "10%" in report_path.read_text()
