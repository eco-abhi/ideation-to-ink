"""Hand-authored pipeline topology for the flow diagram.

Deliberately NOT introspected from engine.graphs.master.build_master_graph():
LangGraph's compiled graph doesn't expose a clean frontend-friendly node/edge
list, and introspecting its internals would couple this presentation layer to
LangGraph internals. Trade-off: this can drift from the real graph if
graphs/*.py changes without a matching update here -- mitigated by
tests/test_topology.py, which compiles the real master graph and asserts every
node id below actually exists in it.

Node order matters beyond display: flow_status.py uses it as a linear
approximation of pipeline position to infer which un-logged gate/plumbing
nodes were silently passed through. See that module's docstring for the
revision-loop limitation this implies.
"""

from __future__ import annotations

from web.backend.schemas import TopologyEdge, TopologyNode

NODES: list[TopologyNode] = [
    # --- Ideation ---
    TopologyNode(id="literature_scout", label="literature_scout", phase="ideation", kind="agent"),
    TopologyNode(id="novelty_checker", label="novelty_checker", phase="ideation", kind="agent"),
    TopologyNode(id="novelty_human_gate", label="novelty verdict", phase="ideation", kind="gate"),
    TopologyNode(id="rq_refiner", label="rq_refiner", phase="ideation", kind="agent"),
    TopologyNode(id="venue_strategist", label="venue_strategist", phase="ideation", kind="agent"),
    TopologyNode(id="ideation_complete", label="ideation complete", phase="ideation", kind="plumbing"),
    # --- Experiments ---
    TopologyNode(id="methodology_designer", label="methodology_designer", phase="experiments", kind="agent"),
    TopologyNode(id="methodology_human_gate", label="methodology approval", phase="experiments", kind="gate"),
    TopologyNode(id="experiment_scaffolder", label="experiment_scaffolder", phase="experiments", kind="agent"),
    TopologyNode(id="results_gate", label="awaiting results", phase="experiments", kind="gate"),
    TopologyNode(id="stats_validator", label="stats_validator", phase="experiments", kind="agent"),
    TopologyNode(id="experiments_complete", label="experiments complete", phase="experiments", kind="plumbing"),
    # --- Writing ---
    TopologyNode(id="structure_agent", label="structure_agent", phase="writing", kind="agent"),
    TopologyNode(id="section_drafters", label="section_drafters", phase="writing", kind="agent"),
    TopologyNode(id="citation_verifier", label="citation_verifier", phase="writing", kind="agent"),
    TopologyNode(id="citation_human_gate", label="suspicious citations", phase="writing", kind="gate"),
    TopologyNode(id="writing_complete", label="writing complete", phase="writing", kind="plumbing"),
    # --- Review ---
    TopologyNode(id="adversarial_reviewer_ensemble", label="adversarial_reviewer_ensemble", phase="review", kind="agent"),
    TopologyNode(id="claims_evidence_auditor", label="claims_evidence_auditor", phase="review", kind="agent"),
    TopologyNode(id="flow_checker", label="flow_checker", phase="review", kind="agent"),
    TopologyNode(id="compliance_checker", label="compliance_checker", phase="review", kind="agent"),
    TopologyNode(id="revision_router", label="revision_router", phase="review", kind="agent"),
    TopologyNode(id="revision_max_loops_gate", label="revision cap reached", phase="review", kind="gate"),
    TopologyNode(id="review_complete", label="done", phase="review", kind="plumbing"),
    # --- Cross-cutting: reachable from any agent node on failure, not wired via normal edges ---
    TopologyNode(id="error_gate", label="error (any node)", phase="cross-cutting", kind="gate"),
]

EDGES: list[TopologyEdge] = [
    TopologyEdge(source="literature_scout", target="novelty_checker"),
    TopologyEdge(source="novelty_checker", target="novelty_human_gate"),
    TopologyEdge(source="novelty_human_gate", target="rq_refiner", label="proceed"),
    TopologyEdge(source="rq_refiner", target="venue_strategist"),
    TopologyEdge(source="venue_strategist", target="ideation_complete"),
    TopologyEdge(source="ideation_complete", target="methodology_designer"),
    TopologyEdge(source="methodology_designer", target="methodology_human_gate"),
    TopologyEdge(source="methodology_human_gate", target="experiment_scaffolder", label="approve"),
    TopologyEdge(source="experiment_scaffolder", target="results_gate"),
    TopologyEdge(source="results_gate", target="stats_validator"),
    TopologyEdge(source="stats_validator", target="experiments_complete"),
    TopologyEdge(source="experiments_complete", target="structure_agent"),
    TopologyEdge(source="structure_agent", target="section_drafters"),
    TopologyEdge(source="section_drafters", target="citation_verifier"),
    TopologyEdge(source="citation_verifier", target="citation_human_gate"),
    TopologyEdge(source="citation_human_gate", target="writing_complete"),
    TopologyEdge(source="writing_complete", target="adversarial_reviewer_ensemble"),
    TopologyEdge(source="adversarial_reviewer_ensemble", target="claims_evidence_auditor"),
    TopologyEdge(source="claims_evidence_auditor", target="flow_checker"),
    TopologyEdge(source="flow_checker", target="compliance_checker"),
    TopologyEdge(source="compliance_checker", target="revision_router"),
    TopologyEdge(source="revision_router", target="section_drafters", label="major concerns (loop)"),
    TopologyEdge(source="revision_router", target="revision_max_loops_gate", label="3 loops used"),
    TopologyEdge(source="revision_router", target="review_complete", label="converged"),
    TopologyEdge(source="revision_max_loops_gate", target="review_complete", label="force_done"),
]

# HUMAN_INPUT_NEEDED.json's "type" field -> the gate node id that produced it.
INTERRUPT_TYPE_TO_GATE: dict[str, str] = {
    "novelty_verdict": "novelty_human_gate",
    "methodology_approval": "methodology_human_gate",
    "awaiting_experiment_results": "results_gate",
    "suspicious_citations": "citation_human_gate",
    "revision_cap_reached": "revision_max_loops_gate",
    "node_error": "error_gate",
}
