"""The only sanctioned way to turn an agent function into a LangGraph node.

graphs/*.py must never call `builder.add_node(name, some_agent_fn)` directly --
always `builder.add_node(name, traced_node(name, some_agent_fn, skill=...))`.
This is what makes "no node runs unlogged" and "node exceptions never silently
continue" true by construction rather than by convention.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any

from langgraph.types import interrupt

from engine.agents.base import AgentFn
from engine.prompts.loader import SkillRef
from engine.provenance import ProvenanceEntry, hash_input, log_provenance
from engine.state import PaperState

ERROR_GATE = "error_gate"


def traced_node(
    agent_name: str, fn: AgentFn, *, skill: SkillRef | None = None
) -> Callable[[PaperState], dict[str, Any]]:
    def wrapped(state: PaperState) -> dict[str, Any]:
        start = time.monotonic()
        input_hash = hash_input(state.model_dump(mode="json"))
        try:
            result = fn(state)
        except Exception as exc:  # fail-loud boundary: never let a node crash the process silently
            duration_ms = int((time.monotonic() - start) * 1000)
            message = f"{agent_name}: {exc.__class__.__name__}: {exc}"
            log_provenance(
                ProvenanceEntry(
                    paper_id=state.paper_id,
                    agent=agent_name,
                    model=None,
                    skill_name=skill.name if skill else None,
                    skill_upstream_commit=skill.upstream_commit if skill else None,
                    input_hash=input_hash,
                    output_summary="",
                    tokens={},
                    artifacts_written=[],
                    duration_ms=duration_ms,
                    error=message,
                )
            )
            return {"errors": [message]}

        duration_ms = int((time.monotonic() - start) * 1000)
        log_provenance(
            ProvenanceEntry(
                paper_id=state.paper_id,
                agent=agent_name,
                model=result.model,
                skill_name=skill.name if skill else None,
                skill_upstream_commit=skill.upstream_commit if skill else None,
                input_hash=input_hash,
                output_summary=result.output_summary,
                tokens={"prompt": result.prompt_tokens, "completion": result.completion_tokens},
                artifacts_written=result.artifacts_written,
                duration_ms=duration_ms,
                error=None,
            )
        )
        return result.update

    return wrapped


def has_unacknowledged_errors(state: PaperState) -> bool:
    return len(state.errors) > state.errors_acknowledged_count


def route_after(success_target: str) -> Callable[[PaperState], str]:
    """Conditional-edge factory: go to `success_target` unless the node that just
    ran left new, unacknowledged errors, in which case detour to the error gate.
    """

    def _route(state: PaperState) -> str:
        return ERROR_GATE if has_unacknowledged_errors(state) else success_target

    return _route


def error_gate(state: PaperState) -> dict[str, Any]:
    """Reached whenever a traced node fails. Surfaces new errors to the human via
    interrupt(); on --resume, acknowledges them and ends the run. Since the
    triggering phase never advanced, the next `engine run --resume` re-enters at
    the same phase and naturally retries the failed step.
    """
    interrupt(
        {
            "type": "node_error",
            "paper_id": state.paper_id,
            "unacknowledged_errors": state.errors[state.errors_acknowledged_count :],
        }
    )
    return {"errors_acknowledged_count": len(state.errors)}
