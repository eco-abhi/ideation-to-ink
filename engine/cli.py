"""CLI entrypoint: python -m engine <new|run|import|check> ..."""

from __future__ import annotations

import argparse
import sys

from engine.tools.workspace import scaffold_workspace


def cmd_new(args: argparse.Namespace) -> None:
    try:
        scaffold_workspace(args.slug, topic=args.topic)
    except FileExistsError as exc:
        raise SystemExit(str(exc)) from exc
    print(f"Scaffolded papers/{args.slug}/")


def cmd_run(args: argparse.Namespace) -> None:
    from engine.graphs.master import run_paper

    run_paper(args.slug, target_phase=args.phase, resume=args.resume)


def cmd_import(args: argparse.Namespace) -> None:
    from engine.agents.importer import import_paper

    import_paper(args.slug, source_dir=args.from_dir)


def cmd_check(args: argparse.Namespace) -> None:
    from engine.graphs.master import run_single_agent

    run_single_agent(args.slug, agent_name=args.agent)


def cmd_costs(args: argparse.Namespace) -> None:
    from engine.provenance import format_usage_table

    print(format_usage_table(args.slug, by_model=args.by_model))


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

    p_costs = sub.add_parser("costs", help="Show token usage and cost, aggregated from provenance/run_log.jsonl")
    p_costs.add_argument("slug")
    p_costs.add_argument("--by-model", action="store_true", help="Break down by agent+model instead of just agent")
    p_costs.set_defaults(func=cmd_costs)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    args.func(args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
