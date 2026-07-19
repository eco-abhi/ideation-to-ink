"""Single choke point for every artifact write. No node writes files any other way.

Enforces:
  - all writes stay under papers/<paper_id>/
  - restricted paths (currently refs.bib) are only writable by their allowlisted agent
  - LaTeX/BibTeX writes reject shell-escape and absolute-path-include constructs, since
    LLM-authored .tex is later fed to pdflatex
"""

from __future__ import annotations

import re

from engine.config import PAPERS_ROOT

# relpath (posix, relative to papers/<paper_id>/) -> agents allowed to write it
ARTIFACT_WRITE_POLICY: dict[str, set[str]] = {
    "manuscript/refs.bib": {"citation_verifier"},
}

_DANGEROUS_LATEX_PATTERNS = [
    re.compile(r"\\write18"),
    re.compile(r"\\immediate\s*\\write18"),
    re.compile(r"\\input\s*\{\s*/"),
    re.compile(r"\\include\s*\{\s*/"),
    re.compile(r"\\catcode.*\\active"),  # active-char redefinition, common injection vector
]

_LATEX_SPECIAL_CHARS = {
    "&": r"\&",
    "%": r"\%",
    "$": r"\$",
    "#": r"\#",
    "_": r"\_",
    "{": r"\{",
    "}": r"\}",
    "~": r"\textasciitilde{}",
    "^": r"\textasciicircum{}",
    "\\": r"\textbackslash{}",
}


class ArtifactWriteError(PermissionError):
    pass


class UnsafeLatexError(ValueError):
    pass


def latex_escape(text: str) -> str:
    """Escape special characters in a plain-text string meant to be interpolated
    into a .tex/.bib file (e.g. a title pulled from an API). Do NOT run this over
    LLM-authored LaTeX body text -- it would mangle legitimate commands.
    """
    return "".join(_LATEX_SPECIAL_CHARS.get(ch, ch) for ch in text)


def _check_latex_safety(relpath: str, content: str) -> None:
    if not relpath.endswith((".tex", ".bib")):
        return
    for pattern in _DANGEROUS_LATEX_PATTERNS:
        if pattern.search(content):
            raise UnsafeLatexError(
                f"Refusing to write {relpath}: matched forbidden pattern {pattern.pattern!r}"
            )


def resolve_path(paper_id: str, relpath: str):
    paper_root = (PAPERS_ROOT / paper_id).resolve()
    target = (paper_root / relpath).resolve()
    if paper_root not in target.parents and target != paper_root:
        raise ArtifactWriteError(f"{relpath!r} resolves outside papers/{paper_id}/")
    return target


def prepare_path(paper_id: str, relpath: str, *, caller_agent: str | None = None):
    """Like resolve_path, but also enforces ARTIFACT_WRITE_POLICY and creates the
    parent directory. For binary artifacts (parquet, figures) that can't go through
    safe_write's text-based LaTeX checks -- the caller writes bytes to the returned
    path itself.
    """
    normalized = relpath.replace("\\", "/").lstrip("/")
    allowed = ARTIFACT_WRITE_POLICY.get(normalized)
    if allowed is not None and caller_agent not in allowed:
        raise ArtifactWriteError(
            f"{caller_agent!r} is not allowed to write {normalized!r}; only {sorted(allowed)} may"
        )
    target = resolve_path(paper_id, normalized)
    target.parent.mkdir(parents=True, exist_ok=True)
    return target


def safe_write(paper_id: str, relpath: str, content: str, *, caller_agent: str):
    """Write `content` to papers/<paper_id>/<relpath>, enforcing guardrails.

    Returns the resolved Path written.
    """
    normalized = relpath.replace("\\", "/").lstrip("/")
    allowed = ARTIFACT_WRITE_POLICY.get(normalized)
    if allowed is not None and caller_agent not in allowed:
        raise ArtifactWriteError(
            f"{caller_agent!r} is not allowed to write {normalized!r}; only {sorted(allowed)} may"
        )

    target = resolve_path(paper_id, normalized)
    _check_latex_safety(normalized, content)

    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content)
    return target
