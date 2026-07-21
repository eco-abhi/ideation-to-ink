"""Computes per-node status for the flow diagram from files already on disk --
no engine changes, no new state. See topology.py's docstring for the hand-authored
topology this maps onto.

Limitation: gate/plumbing nodes (novelty_human_gate, writing_complete, etc.) are
never traced/logged to provenance -- only the 17 real agents are. So a gate that
passed through silently (e.g. citation_human_gate when nothing was suspicious)
leaves no trace. This is worked around with a position heuristic: topology.NODES
is authored in linear pipeline order, and any node earlier than the furthest
agent with a logged entry is assumed completed. That heuristic is imprecise
across a revision loop (section_drafters etc. re-run, but everything after them
in list order already shows "completed" from the first pass) -- acceptable for
a v1 status glance; provenance/costs endpoints give the precise detail.
"""

from __future__ import annotations

import json

from engine.config import paper_dir
from engine.provenance import read_provenance
from web.backend import topology
from web.backend.schemas import FlowNodeStatus, FlowStatus


def compute_flow_status(paper_id: str) -> FlowStatus:
    entries = read_provenance(paper_id)

    agent_status: dict[str, str] = {}
    for entry in entries:  # file order == chronological; last occurrence wins
        agent_status[entry.agent] = "failed" if entry.error else "completed"

    paused_gate: str | None = None
    gate_payload: dict | None = None
    human_input_path = paper_dir(paper_id) / "HUMAN_INPUT_NEEDED.json"
    if human_input_path.exists():
        gate_payload = json.loads(human_input_path.read_text())
        paused_gate = topology.INTERRUPT_TYPE_TO_GATE.get(gate_payload.get("type"))

    order = [n.id for n in topology.NODES]
    reached_idx = max(
        (i for i, node_id in enumerate(order) if agent_status.get(node_id) in ("completed", "failed")),
        default=-1,
    )

    node_status: list[FlowNodeStatus] = []
    for i, node_id in enumerate(order):
        if node_id == paused_gate:
            status = "paused"
        elif node_id in agent_status:
            status = agent_status[node_id]
        elif i < reached_idx:
            status = "completed"  # un-logged gate/plumbing node silently passed
        else:
            status = "pending"
        node_status.append(FlowNodeStatus(id=node_id, status=status))

    return FlowStatus(
        paper_id=paper_id,
        nodes=topology.NODES,
        edges=topology.EDGES,
        node_status=node_status,
        paused_gate=paused_gate,
        gate_payload=gate_payload,
    )
