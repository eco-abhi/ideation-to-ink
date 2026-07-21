"""Paper workspace scaffolding, shared by `engine new` and `engine import`."""

from __future__ import annotations

import yaml

from engine.config import paper_dir

WORKSPACE_SUBDIRS = [
    "ideation",
    "experiments/src",
    "experiments/data",
    "experiments/results",
    "experiments/env",
    "manuscript/sections",
    "manuscript/figures",
    "reviews",
    "provenance",
]


def scaffold_workspace(
    slug: str,
    *,
    topic: str,
    keywords: list[str] | None = None,
    abstract: str | None = None,
    phase: str = "ideation",
    status: str = "new",
    extra_yaml: dict | None = None,
) -> None:
    """Create papers/<slug>/ with the standard subdirectories and a paper.yaml.
    Raises if the workspace already exists -- callers that want to add to an
    existing workspace (e.g. import onto a pre-scaffolded slug) should check first.

    `topic` doubles as the paper's short working title -- it's what
    literature_scout uses as a literal search query, so keep it short.
    `abstract`/`keywords` are long-form context for LLM prompts only, never
    sent to a search API as-is.
    """
    pdir = paper_dir(slug)
    if pdir.exists():
        raise FileExistsError(f"papers/{slug}/ already exists")

    for sub in WORKSPACE_SUBDIRS:
        (pdir / sub).mkdir(parents=True, exist_ok=True)

    (pdir / "provenance" / "run_log.jsonl").touch()
    (pdir / "manuscript" / "refs.bib").write_text("")
    (pdir / "manuscript" / "refs_draft.bib").write_text("")

    paper_yaml = {
        "paper_id": slug,
        "topic": topic,
        "keywords": keywords or [],
        "abstract": abstract,
        "venue": None,
        "deadline": None,
        "phase": phase,
        "status": status,
        **(extra_yaml or {}),
    }
    (pdir / "paper.yaml").write_text(yaml.safe_dump(paper_yaml, sort_keys=False))


def load_paper_yaml(slug: str) -> dict:
    path = paper_dir(slug) / "paper.yaml"
    if not path.exists():
        raise FileNotFoundError(f"papers/{slug}/paper.yaml not found -- run `engine new {slug} --topic ...` first")
    return yaml.safe_load(path.read_text())


def save_paper_yaml(slug: str, doc: dict) -> None:
    (paper_dir(slug) / "paper.yaml").write_text(yaml.safe_dump(doc, sort_keys=False))
