"""CLI entrypoint: python -m engine <new|run|import|check> ..."""

from __future__ import annotations

import argparse
import sys

import yaml

from engine.config import paper_dir

_WORKSPACE_SUBDIRS = [
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


def cmd_new(args: argparse.Namespace) -> None:
    slug = args.slug
    pdir = paper_dir(slug)
    if pdir.exists():
        raise SystemExit(f"papers/{slug}/ already exists")

    for sub in _WORKSPACE_SUBDIRS:
        (pdir / sub).mkdir(parents=True, exist_ok=True)

    (pdir / "provenance" / "run_log.jsonl").touch()
    (pdir / "manuscript" / "refs.bib").write_text("")

    paper_yaml = {
        "paper_id": slug,
        "topic": args.topic,
        "venue": None,
        "deadline": None,
        "phase": "ideation",
        "status": "new",
    }
    (pdir / "paper.yaml").write_text(yaml.safe_dump(paper_yaml, sort_keys=False))
    print(f"Scaffolded papers/{slug}/")


def cmd_run(args: argparse.Namespace) -> None:
    from engine.graphs.master import run_paper

    run_paper(args.slug, target_phase=args.phase, resume=args.resume)


def cmd_import(args: argparse.Namespace) -> None:
    from engine.agents.importer import import_paper

    import_paper(args.slug, source_dir=args.from_dir)


def cmd_check(args: argparse.Namespace) -> None:
    from engine.graphs.master import run_single_agent

    run_single_agent(args.slug, agent_name=args.agent)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m engine")
    sub = parser.add_subparsers(dest="command", required=True)

    p_new = sub.add_parser("new", help="Scaffold a new paper workspace")
    p_new.add_argument("slug")
    p_new.add_argument("--topic", required=True)
    p_new.set_defaults(func=cmd_new)

    p_run = sub.add_parser("run", help="Run (or resume) the pipeline for a paper")
    p_run.add_argument("slug")
    p_run.add_argument("--phase", default=None, help="Force entry at this phase")
    p_run.add_argument("--resume", action="store_true", help="Resume from the last checkpoint")
    p_run.set_defaults(func=cmd_run)

    p_import = sub.add_parser("import", help="Import an existing draft into a paper workspace")
    p_import.add_argument("slug")
    p_import.add_argument("--from", dest="from_dir", required=True)
    p_import.set_defaults(func=cmd_import)

    p_check = sub.add_parser("check", help="Run a single agent against the current workspace")
    p_check.add_argument("slug")
    p_check.add_argument("--agent", required=True)
    p_check.set_defaults(func=cmd_check)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    args.func(args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
