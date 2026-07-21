"""Response models for the read-only dashboard API. Mirrors PaperState/ProvenanceEntry
shapes where useful but never imports engine write-paths -- this package only reads."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel

NodeKind = Literal["agent", "gate", "plumbing"]
NodeStatus = Literal["pending", "completed", "failed", "paused"]


class TopologyNode(BaseModel):
    id: str
    label: str
    phase: str
    kind: NodeKind


class TopologyEdge(BaseModel):
    source: str
    target: str
    label: str | None = None


class FlowNodeStatus(BaseModel):
    id: str
    status: NodeStatus


class FlowStatus(BaseModel):
    paper_id: str
    nodes: list[TopologyNode]
    edges: list[TopologyEdge]
    node_status: list[FlowNodeStatus]
    paused_gate: str | None = None
    gate_payload: dict[str, Any] | None = None


class PaperSummary(BaseModel):
    paper_id: str
    topic: str
    venue: str | None = None
    phase: str
    status: str


class PaperDetail(PaperSummary):
    revision_loop_count: int = 0
    errors: list[str] = []
    artifacts: dict[str, str] = {}
    paused: bool = False
    gate_payload: dict[str, Any] | None = None
    running: bool = False
