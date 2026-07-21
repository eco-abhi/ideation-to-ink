"""Append-only JSONL provenance log: one line per node execution, no exceptions."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field

from engine.config import paper_dir


class ProvenanceEntry(BaseModel):
    ts: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    paper_id: str
    agent: str
    model: str | None = None
    skill_name: str | None = None
    skill_upstream_commit: str | None = None
    input_hash: str
    output_summary: str
    tokens: dict[str, int] = Field(default_factory=dict)
    cost_usd: float | None = None
    artifacts_written: list[str] = Field(default_factory=list)
    duration_ms: int
    error: str | None = None


def hash_input(payload: Any) -> str:
    blob = json.dumps(payload, sort_keys=True, default=str).encode()
    return hashlib.sha256(blob).hexdigest()[:16]


def log_provenance(entry: ProvenanceEntry) -> None:
    log_path = paper_dir(entry.paper_id) / "provenance" / "run_log.jsonl"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a") as f:
        f.write(entry.model_dump_json() + "\n")


def read_provenance(paper_id: str) -> list[ProvenanceEntry]:
    log_path = paper_dir(paper_id) / "provenance" / "run_log.jsonl"
    if not log_path.exists():
        return []
    entries = []
    with log_path.open() as f:
        for line in f:
            line = line.strip()
            if line:
                entries.append(ProvenanceEntry.model_validate_json(line))
    return entries


class UsageRow(BaseModel):
    key: str  # "<agent>" or "<agent>/<model>" depending on grouping
    calls: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cost_usd: float = 0.0
    cost_unknown_calls: int = 0  # calls where cost_usd couldn't be computed (unrecognized model pricing)


def summarize_usage(entries: list[ProvenanceEntry], *, by_model: bool = False) -> list[UsageRow]:
    """Aggregate token/cost usage per agent (or per agent+model). Skips entries
    with no model (deterministic, non-LLM nodes like experiment_scaffolder) so
    they don't pollute a cost report with zero-cost noise.
    """
    rows: dict[str, UsageRow] = {}
    for entry in entries:
        if entry.model is None:
            continue
        key = f"{entry.agent}/{entry.model}" if by_model else entry.agent
        row = rows.setdefault(key, UsageRow(key=key))
        row.calls += 1
        row.prompt_tokens += entry.tokens.get("prompt", 0)
        row.completion_tokens += entry.tokens.get("completion", 0)
        if entry.cost_usd is None:
            row.cost_unknown_calls += 1
        else:
            row.cost_usd += entry.cost_usd
    return sorted(rows.values(), key=lambda r: r.cost_usd, reverse=True)


def total_usage(entries: list[ProvenanceEntry]) -> UsageRow:
    total = UsageRow(key="TOTAL")
    for row in summarize_usage(entries):
        total.calls += row.calls
        total.prompt_tokens += row.prompt_tokens
        total.completion_tokens += row.completion_tokens
        total.cost_usd += row.cost_usd
        total.cost_unknown_calls += row.cost_unknown_calls
    return total


def format_usage_table(paper_id: str, *, by_model: bool = False) -> str:
    entries = read_provenance(paper_id)
    rows = summarize_usage(entries, by_model=by_model)
    if not rows:
        return f"No LLM usage recorded yet for {paper_id!r} (provenance/run_log.jsonl is empty or has no LLM calls)."

    total = total_usage(entries)
    header = f"{'agent' if not by_model else 'agent/model':40s} {'calls':>6s} {'prompt':>10s} {'completion':>11s} {'cost_usd':>10s}"
    lines = [header, "-" * len(header)]
    for row in rows:
        cost_str = f"{row.cost_usd:.4f}" + ("*" if row.cost_unknown_calls else "")
        lines.append(f"{row.key:40s} {row.calls:6d} {row.prompt_tokens:10d} {row.completion_tokens:11d} {cost_str:>10s}")
    lines.append("-" * len(header))
    total_cost_str = f"{total.cost_usd:.4f}" + ("*" if total.cost_unknown_calls else "")
    lines.append(f"{'TOTAL':40s} {total.calls:6d} {total.prompt_tokens:10d} {total.completion_tokens:11d} {total_cost_str:>10s}")
    if total.cost_unknown_calls:
        lines.append(
            f"\n* {total.cost_unknown_calls} call(s) have unknown cost (litellm has no pricing data for "
            "that model) and are excluded from the cost total above."
        )
    return "\n".join(lines)
