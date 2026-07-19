"""The single wrapper every agent must call through for model access.

Provider-agnostic via LiteLLM: swapping models is a config change
(engine.config.DEFAULT_LLM_MODEL / AGENT_MODEL_OVERRIDES), never a code change.
Every call returns token counts so the caller can forward them to NodeResult ->
provenance; nothing is logged silently inside this module.
"""

from __future__ import annotations

import json
import re
from typing import Any, TypeVar

import litellm
from pydantic import BaseModel

from engine.config import EMBEDDING_MODEL, model_for_agent

Message = dict[str, str]
T = TypeVar("T", bound=BaseModel)

_CODE_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)


class LLMResult(BaseModel):
    content: str
    model: str
    prompt_tokens: int
    completion_tokens: int
    cost_usd: float | None = None


def call_llm(
    messages: list[Message],
    *,
    agent_name: str,
    model: str | None = None,
    temperature: float = 0.2,
    **kwargs: Any,
) -> LLMResult:
    resolved_model = model or model_for_agent(agent_name)
    response = litellm.completion(
        model=resolved_model, messages=messages, temperature=temperature, **kwargs
    )
    usage = response.usage
    try:
        cost = litellm.completion_cost(completion_response=response)
    except Exception:
        cost = None
    return LLMResult(
        content=response.choices[0].message.content or "",
        model=resolved_model,
        prompt_tokens=getattr(usage, "prompt_tokens", 0) or 0,
        completion_tokens=getattr(usage, "completion_tokens", 0) or 0,
        cost_usd=cost,
    )


def _strip_code_fences(text: str) -> str:
    return _CODE_FENCE_RE.sub("", text).strip()


def call_llm_json(
    messages: list[Message],
    *,
    agent_name: str,
    schema: type[T],
    model: str | None = None,
    temperature: float = 0.2,
    max_retries: int = 1,
    **kwargs: Any,
) -> tuple[T, LLMResult]:
    """Call the model and parse its reply as `schema`, retrying with the parse
    error fed back to the model on failure.
    """
    working_messages = [
        *messages,
        {
            "role": "system",
            "content": (
                "Respond with ONLY valid JSON matching this schema, no prose, no "
                f"markdown fences:\n{json.dumps(schema.model_json_schema())}"
            ),
        },
    ]
    last_result: LLMResult | None = None
    last_err: Exception | None = None
    for _ in range(max_retries + 1):
        last_result = call_llm(
            working_messages, agent_name=agent_name, model=model, temperature=temperature, **kwargs
        )
        try:
            parsed = schema.model_validate_json(_strip_code_fences(last_result.content))
            return parsed, last_result
        except Exception as exc:  # noqa: BLE001 -- feed any parse/validation failure back to the model
            last_err = exc
            working_messages = [
                *working_messages,
                {"role": "assistant", "content": last_result.content},
                {
                    "role": "user",
                    "content": f"That was not valid JSON matching the schema ({exc}). "
                    "Reply again with ONLY the corrected JSON.",
                },
            ]
    raise ValueError(
        f"call_llm_json: failed to get a valid {schema.__name__} after "
        f"{max_retries + 1} attempt(s): {last_err}"
    )


def embed_texts(texts: list[str], *, model: str | None = None) -> list[list[float]]:
    resolved_model = model or EMBEDDING_MODEL
    response = litellm.embedding(model=resolved_model, input=texts)
    return [item["embedding"] for item in response.data]
