"""Standalone audit agent (skill: paper-redline-diff): diff manuscript/sections/*.tex
against the last git commit. Invoked via `python -m engine check --agent redline_diff`,
not part of the automated pipeline -- see revision_router.py's docstring for why
diffing lives here instead of in the automated revision loop (there's nothing to
diff against until a redraft has actually happened and been committed).
"""

from __future__ import annotations

import difflib
import subprocess

from engine.agents.base import NodeResult
from engine.config import paper_dir
from engine.prompts.loader import skill_ref
from engine.state import PaperState
from engine.tools import fs_guard

AGENT_NAME = "redline_diff"
SKILL = skill_ref("paper-redline-diff")

REPORT_RELPATH = "manuscript/redline_diff.md"


def _git_show_head(paper_id: str, relpath: str) -> str | None:
    try:
        result = subprocess.run(
            ["git", "show", f"HEAD:papers/{paper_id}/{relpath}"],
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return result.stdout if result.returncode == 0 else None


def redline_diff(state: PaperState) -> NodeResult:
    sections_dir = paper_dir(state.paper_id) / "manuscript" / "sections"
    if not sections_dir.exists():
        raise ValueError("no manuscript/sections/ found to diff")

    diff_blocks = []
    for tex_file in sorted(sections_dir.glob("*.tex")):
        relpath = f"manuscript/sections/{tex_file.name}"
        old_text = _git_show_head(state.paper_id, relpath) or ""
        new_text = tex_file.read_text()
        if old_text == new_text:
            continue
        diff_lines = list(
            difflib.unified_diff(
                old_text.splitlines(keepends=True),
                new_text.splitlines(keepends=True),
                fromfile=f"HEAD:{relpath}",
                tofile=f"working:{relpath}",
            )
        )
        if diff_lines:
            diff_blocks.append(f"## {tex_file.stem}\n\n```diff\n{''.join(diff_lines)}```")

    body = "\n\n".join(diff_blocks) if diff_blocks else "No changes since the last commit."
    report = f"# Redline Diff (working tree vs. HEAD)\n\n{body}"
    fs_guard.safe_write(state.paper_id, REPORT_RELPATH, report, caller_agent=AGENT_NAME)

    return NodeResult(
        update={},
        artifacts_written=[REPORT_RELPATH],
        output_summary=f"{len(diff_blocks)} section(s) changed since HEAD",
    )
