"""Loads vendored skill prompts and project-local suffixes.

Vendored skills live under prompts/vendored/re-paper-writing/skills/<name>/SKILL.md
and are never edited in place -- overrides and additions belong in prompts/local/.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import cache, lru_cache
from pathlib import Path

PROMPTS_ROOT = Path(__file__).resolve().parent
VENDORED_ROOT = PROMPTS_ROOT / "vendored" / "re-paper-writing"
SKILLS_ROOT = VENDORED_ROOT / "skills"
LOCAL_ROOT = PROMPTS_ROOT / "local"

_FRONTMATTER_RE = re.compile(r"\A---\n.*?\n---\n", re.DOTALL)


@dataclass(frozen=True)
class SkillRef:
    """Identifies a prompt source for provenance logging.

    `upstream_commit` is None for locally-authored skills/suffixes that have
    no vendored counterpart (e.g. novelty_checker's STOP-gate prompt).
    """

    name: str
    upstream_commit: str | None = None


@lru_cache(maxsize=1)
def upstream_commit() -> str:
    return (VENDORED_ROOT / "UPSTREAM_COMMIT").read_text().strip()


def skill_ref(name: str) -> SkillRef:
    """A SkillRef for a vendored skill, stamped with the current UPSTREAM_COMMIT."""
    return SkillRef(name=name, upstream_commit=upstream_commit())


def local_ref(name: str) -> SkillRef:
    """A SkillRef for a locally-authored (non-vendored) prompt."""
    return SkillRef(name=name, upstream_commit=None)


@cache
def load_skill(name: str) -> str:
    """Return the body (frontmatter stripped) of a vendored SKILL.md."""
    path = SKILLS_ROOT / name / "SKILL.md"
    if not path.exists():
        raise FileNotFoundError(f"Vendored skill {name!r} not found at {path}")
    text = path.read_text()
    return _FRONTMATTER_RE.sub("", text, count=1).strip()


@cache
def load_local_suffix(name: str) -> str:
    """Return a project-authored prompt suffix from prompts/local/<name>.md."""
    path = LOCAL_ROOT / f"{name}.md"
    if not path.exists():
        raise FileNotFoundError(f"Local prompt suffix {name!r} not found at {path}")
    return path.read_text().strip()


def build_system_prompt(
    *,
    skills: list[str] | None = None,
    local_suffix: str | None = None,
    context: dict[str, object] | None = None,
) -> str:
    """Concatenate vendored skill bodies with a rendered local suffix.

    `context` values are interpolated into the local suffix via str.format;
    unresolved placeholders in the suffix are a template bug, not swallowed.
    """
    parts = [load_skill(name) for name in (skills or [])]
    if local_suffix:
        suffix = load_local_suffix(local_suffix)
        if context:
            suffix = suffix.format(**context)
        parts.append(suffix)
    return "\n\n---\n\n".join(parts)
