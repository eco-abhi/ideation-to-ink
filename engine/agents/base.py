"""The return contract every agent node function implements.

An agent function is `(PaperState) -> NodeResult`. It never writes to state
directly and never calls the provenance logger itself -- graphs/_registry.traced_node
does both, using the fields on NodeResult. This keeps "no node runs unlogged" true
by construction: there is no code path to register a node with LangGraph that
skips the wrapper.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from pydantic import BaseModel, Field

from engine.state import PaperState


class NodeResult(BaseModel):
    update: dict[str, Any] = Field(default_factory=dict)
    model: str | None = None
    prompt_tokens: int = 0
    completion_tokens: int = 0
    artifacts_written: list[str] = Field(default_factory=list)
    output_summary: str = ""


AgentFn = Callable[[PaperState], NodeResult]
