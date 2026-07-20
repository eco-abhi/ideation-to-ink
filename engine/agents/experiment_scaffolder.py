"""Phase 2 agent 2: generate experiments/src/ skeleton, env/requirements.lock,
seeds.json from the approved DESIGN.md. Purely mechanical -- no LLM call, since
scaffolding a skeleton doesn't need one and every other node's cost should buy
something an LLM is actually needed for. Execution of the scaffold is
human/Claude-Code-driven, outside this graph; graphs/experiments.py's
results_gate node is what waits for experiments/results/metrics.json to appear.
"""

from __future__ import annotations

import json

from engine.agents.base import NodeResult
from engine.config import paper_dir
from engine.state import PaperState
from engine.tools import fs_guard

AGENT_NAME = "experiment_scaffolder"
SKILL = None  # no vendored skill maps cleanly onto pure scaffolding; see stats_validator for experiment-report-bridge

RUN_STUB_RELPATH = "experiments/src/run_experiment.py"
REQUIREMENTS_RELPATH = "experiments/env/requirements.lock"
SEEDS_RELPATH = "experiments/seeds.json"

DEFAULT_SEEDS = [0, 1, 2]
DEFAULT_REQUIREMENTS = ["numpy", "pandas", "scikit-learn", "scipy"]


def _design_text(paper_id: str) -> str:
    design_path = paper_dir(paper_id) / "experiments" / "DESIGN.md"
    return design_path.read_text() if design_path.exists() else "(no experiments/DESIGN.md found)"


def experiment_scaffolder(state: PaperState) -> NodeResult:
    design_text = _design_text(state.paper_id)

    run_stub = '\n'.join(
        [
            '"""Experiment runner skeleton -- fill in per experiments/DESIGN.md and run manually.',
            "",
            "This pipeline does not execute experiments itself (out of scope by design --",
            "see the repo README). Run this script (or your own harness) against the",
            "baselines/ablations/metrics below, then write results to",
            "experiments/results/metrics.json for stats_validator to pick up.",
            '"""',
            "",
            "# --- Design summary (from experiments/DESIGN.md) ---",
            *[f"# {line}" for line in design_text.splitlines()],
            "",
            "import json",
            "from pathlib import Path",
            "",
            "SEEDS_PATH = Path(__file__).resolve().parents[1] / 'seeds.json'",
            "RESULTS_PATH = Path(__file__).resolve().parents[1] / 'results' / 'metrics.json'",
            "",
            "",
            "def main() -> None:",
            "    seeds = json.loads(SEEDS_PATH.read_text())",
            "    # TODO: run each baseline/ablation across `seeds`, compute the metrics named",
            "    # in DESIGN.md, and write them (with significance tests + effect sizes) to",
            "    # RESULTS_PATH as JSON. stats_validator checks for exactly that.",
            "    raise NotImplementedError('fill in the experiment loop per experiments/DESIGN.md')",
            "",
            "",
            "if __name__ == '__main__':",
            "    main()",
        ]
    )
    fs_guard.safe_write(state.paper_id, RUN_STUB_RELPATH, run_stub, caller_agent=AGENT_NAME)

    requirements_text = "\n".join(DEFAULT_REQUIREMENTS) + "\n"
    fs_guard.safe_write(state.paper_id, REQUIREMENTS_RELPATH, requirements_text, caller_agent=AGENT_NAME)

    seeds_text = json.dumps(DEFAULT_SEEDS, indent=2) + "\n"
    fs_guard.safe_write(state.paper_id, SEEDS_RELPATH, seeds_text, caller_agent=AGENT_NAME)

    return NodeResult(
        update={
            "artifacts": {
                **state.artifacts,
                "experiment_runner": RUN_STUB_RELPATH,
                "requirements_lock": REQUIREMENTS_RELPATH,
                "seeds": SEEDS_RELPATH,
            }
        },
        artifacts_written=[RUN_STUB_RELPATH, REQUIREMENTS_RELPATH, SEEDS_RELPATH],
        output_summary="scaffolded experiments/src/, env/requirements.lock, seeds.json",
    )
