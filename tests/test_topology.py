"""Guards against web/backend/topology.py drifting from the real graph -- see
that module's docstring for why the topology is hand-authored rather than
introspected.
"""

from engine.graphs.master import build_master_graph
from web.backend import topology


def test_every_topology_node_exists_in_the_real_compiled_graph():
    graph = build_master_graph().compile()
    real_node_ids = set(graph.get_graph().nodes.keys())

    topology_ids = {n.id for n in topology.NODES}
    missing = topology_ids - real_node_ids
    assert not missing, f"topology.py references node(s) not in the real graph: {missing}"


def test_every_topology_edge_endpoint_is_a_known_node():
    node_ids = {n.id for n in topology.NODES}
    for edge in topology.EDGES:
        assert edge.source in node_ids, f"edge source {edge.source!r} not in topology.NODES"
        assert edge.target in node_ids, f"edge target {edge.target!r} not in topology.NODES"


def test_every_interrupt_type_maps_to_a_known_node():
    node_ids = {n.id for n in topology.NODES}
    for interrupt_type, gate_id in topology.INTERRUPT_TYPE_TO_GATE.items():
        assert gate_id in node_ids, f"{interrupt_type!r} maps to unknown node {gate_id!r}"
