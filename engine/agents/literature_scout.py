"""Phase 1 agent 1: query OpenAlex + Semantic Scholar + arXiv, dedupe, write corpus.parquet.

Skills: literature-search (query strategy, ranking heuristics), literature-review
(synthesis framing carried into downstream novelty_checker/rq_refiner prompts).
"""

from __future__ import annotations

from difflib import SequenceMatcher

import pandas as pd
from pydantic import BaseModel, Field

from engine.agents.base import NodeResult
from engine.llm import call_llm_json
from engine.prompts.loader import build_system_prompt, skill_ref
from engine.state import PaperState
from engine.tools import arxiv, fs_guard, openalex, semanticscholar
from engine.tools.common import SearchResult

AGENT_NAME = "literature_scout"
SKILL = skill_ref("literature-search")
TITLE_SIMILARITY_THRESHOLD = 0.90
RESULTS_PER_QUERY_PER_SOURCE = 40


class QueryExpansion(BaseModel):
    queries: list[str] = Field(min_length=1, max_length=4)


def _expand_queries(topic: str) -> tuple[list[str], str, int, int]:
    system_prompt = build_system_prompt(
        skills=["literature-search"],
        local_suffix="literature_scout",
        context={"topic": topic},
    )
    expansion, llm_result = call_llm_json(
        [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Expand this topic into search queries: {topic}"},
        ],
        agent_name=AGENT_NAME,
        schema=QueryExpansion,
    )
    queries = [topic, *expansion.queries]
    return queries, llm_result.model, llm_result.prompt_tokens, llm_result.completion_tokens


def _dedupe(results: list[SearchResult]) -> list[SearchResult]:
    seen_dois: set[str] = set()
    deduped: list[SearchResult] = []
    for r in results:
        if not r.title:
            continue
        if r.doi:
            key = r.doi.lower().strip()
            if key in seen_dois:
                continue
            seen_dois.add(key)
        if any(
            SequenceMatcher(None, r.title.lower(), existing.title.lower()).ratio()
            >= TITLE_SIMILARITY_THRESHOLD
            for existing in deduped
        ):
            continue
        deduped.append(r)
    return deduped


def literature_scout(state: PaperState) -> NodeResult:
    queries, model, prompt_tokens, completion_tokens = _expand_queries(state.topic)

    all_results: list[SearchResult] = []
    for query in queries:
        all_results.extend(openalex.search(query, limit=RESULTS_PER_QUERY_PER_SOURCE))
        all_results.extend(semanticscholar.search(query, limit=RESULTS_PER_QUERY_PER_SOURCE))
        all_results.extend(arxiv.search(query, limit=RESULTS_PER_QUERY_PER_SOURCE))

    deduped = _dedupe(all_results)

    df = pd.DataFrame([r.model_dump() for r in deduped])
    relpath = "ideation/corpus.parquet"
    target = fs_guard.prepare_path(state.paper_id, relpath)
    df.to_parquet(target)

    return NodeResult(
        update={
            "corpus_path": str(target),
            "artifacts": {**state.artifacts, "corpus": relpath},
        },
        model=model,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        artifacts_written=[relpath],
        output_summary=(
            f"{len(queries)} queries -> {len(all_results)} raw results -> "
            f"{len(deduped)} deduped works"
        ),
    )
