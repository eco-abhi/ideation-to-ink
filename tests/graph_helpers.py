"""Shared helpers for building an isolated, testable phase graph (ideation/writing/review/experiments)."""

from __future__ import annotations

from contextlib import contextmanager

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, StateGraph

from engine.graphs._registry import ERROR_GATE, error_gate
from engine.state import PaperState


@contextmanager
def compiled_graph(add_nodes_fn, *, entry_node: str, exit_node: str, db_path: str = ":memory:"):
    """Build a standalone graph from one phase's add_*_nodes function, wired
    START -> entry_node ... -> exit_node -> END, with the shared error_gate -> END.
    Used to test a phase in isolation before graphs/master.py composes all phases.

    Pass a real file path (not ":memory:") to simulate kill-and-resume: compile
    twice against the same db_path in separate `with` blocks.
    """
    builder = StateGraph(PaperState)
    add_nodes_fn(builder)
    builder.add_node(ERROR_GATE, error_gate)
    builder.add_edge(START, entry_node)
    builder.add_edge(exit_node, END)
    builder.add_edge(ERROR_GATE, END)

    with SqliteSaver.from_conn_string(db_path) as checkpointer:
        yield builder.compile(checkpointer=checkpointer)
