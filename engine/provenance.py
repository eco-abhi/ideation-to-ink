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
