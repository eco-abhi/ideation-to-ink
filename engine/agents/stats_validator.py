"""Phase 2 agent 3: validate experiments/results/metrics.json (significance tests,
effect sizes, traceable numbers) and bridge it into a paper-ready results summary
for section_drafters. Folds in experiment-report-bridge here rather than into
experiment_scaffolder -- that skill is about turning *finished* results into a
manuscript handoff, which structurally can't happen before results exist, and
experiment_scaffolder runs before any results do.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from engine.agents.base import NodeResult
from engine.config import paper_dir
from engine.llm import call_llm_json
from engine.prompts.loader import build_system_prompt, skill_ref
from engine.state import PaperState
from engine.tools import fs_guard

AGENT_NAME = "stats_validator"
SKILL = skill_ref("experiment-section-audit")

RESULTS_RELPATH = "experiments/results/metrics.json"
REPORT_RELPATH = "experiments/results_report.md"


class MetricsValidation(BaseModel):
    significance_tests_present: bool
    effect_sizes_reported: bool
    numbers_traceable: bool
    issues: list[str] = Field(default_factory=list)
    results_summary_md: str


def stats_validator(state: PaperState) -> NodeResult:
    results_path = paper_dir(state.paper_id) / RESULTS_RELPATH
    if not results_path.exists():
        raise ValueError(f"{RESULTS_RELPATH} not found -- run the scaffolded experiments first")

    metrics_raw = results_path.read_text()
    design_path = paper_dir(state.paper_id) / "experiments" / "DESIGN.md"
    design_text = design_path.read_text() if design_path.exists() else "(no experiments/DESIGN.md found)"

    system_prompt = build_system_prompt(
        skills=["experiment-section-audit", "table-generation", "academic-plotting", "experiment-report-bridge"],
        local_suffix="stats_validator",
        context={"design": design_text, "metrics_json": metrics_raw[:8000]},
    )
    validation, llm_result = call_llm_json(
        [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": "Audit the results and produce the manuscript handoff."},
        ],
        agent_name=AGENT_NAME,
        schema=MetricsValidation,
    )

    issues = list(validation.issues)
    if not validation.significance_tests_present:
        issues.append("No significance tests found in results/metrics.json")
    if not validation.effect_sizes_reported:
        issues.append("No effect sizes reported in results/metrics.json")
    if not validation.numbers_traceable:
        issues.append("Some reported numbers are not traceable to raw outputs")

    fs_guard.safe_write(state.paper_id, REPORT_RELPATH, validation.results_summary_md, caller_agent=AGENT_NAME)

    return NodeResult(
        update={"artifacts": {**state.artifacts, "results_report": REPORT_RELPATH}},
        model=llm_result.model,
        prompt_tokens=llm_result.prompt_tokens,
        completion_tokens=llm_result.completion_tokens,
        artifacts_written=[REPORT_RELPATH],
        output_summary=f"{len(issues)} issue(s): {'; '.join(issues) if issues else 'none'}",
    )
