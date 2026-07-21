"""Session-wide test isolation.

Real bug this fixes: traced_node (engine/graphs/_registry.py) always calls the
*real* log_provenance() when a graph runs, even if the agent function it wraps
is mocked -- graph-level tests that only patched the agent function (not
PAPERS_ROOT) were writing real papers/<thread_id>/provenance/run_log.jsonl
files into the actual repo on every test run. Caught when papers/demo,
demo-fail, demo-resume, demo-revise, demo-stop kept reappearing after being
git rm'd.

`fs_guard.PAPERS_ROOT` and `config.PAPERS_ROOT` are two independent bindings
(fs_guard does `from engine.config import PAPERS_ROOT`, which copies the
reference at import time -- patching engine.config.PAPERS_ROOT afterward does
NOT change fs_guard's copy). Both must be patched. Functions that call
paper_dir() (defined once in engine.config) *are* fixed transitively by
patching engine.config.PAPERS_ROOT alone, regardless of which module imported
the paper_dir function -- a function's globals resolve against its defining
module, not the caller's.
"""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _isolate_papers_and_checkpoints(tmp_path, monkeypatch):
    import engine.config as config_mod
    from engine.tools import cache, fs_guard

    monkeypatch.setattr(config_mod, "PAPERS_ROOT", tmp_path)
    monkeypatch.setattr(fs_guard, "PAPERS_ROOT", tmp_path)
    monkeypatch.setattr(config_mod, "CHECKPOINTS_ROOT", tmp_path / "_checkpoints")
    monkeypatch.setattr(config_mod, "CACHE_ROOT", tmp_path / "_cache")
    monkeypatch.setattr(cache, "CACHE_ROOT", tmp_path / "_cache")
