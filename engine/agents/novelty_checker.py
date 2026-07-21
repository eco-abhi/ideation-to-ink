"""Phase 1 agent 2: embed the topic vs. corpus abstracts, verdict PROCEED/PIVOT/STOP.

This is the pipeline's differentiator and has no vendored skill counterpart --
prompts/local/novelty_checker.md is authored in-house and its STOP gate must not be
diluted (see that file's rules). A STOP verdict halts the graph in graphs/ideation.py.
"""

from __future__ import annotations

from typing import Literal

import numpy as np
import pandas as pd
from pydantic import BaseModel

from engine.agents.base import NodeResult
from engine.llm import call_llm_json, embed_texts
from engine.prompts.loader import build_system_prompt, local_ref
from engine.state import PaperState
from engine.tools import fs_guard

AGENT_NAME = "novelty_checker"
SKILL = local_ref("novelty_checker")
NEAREST_K = 5


class NoveltyVerdict(BaseModel):
    verdict: Literal["PROCEED", "PIVOT", "STOP"]
    rationale: str


def _cosine_sim(a: np.ndarray, b: np.ndarray) -> float:
    denom = float(np.linalg.norm(a) * np.linalg.norm(b))
    return float(np.dot(a, b) / denom) if denom else 0.0


def novelty_checker(state: PaperState) -> NodeResult:
    if not state.corpus_path:
        raise ValueError("novelty_checker requires corpus_path (run literature_scout first)")

    df = pd.read_parquet(state.corpus_path)
    df = df[df["abstract"].notna() & (df["abstract"].str.len() > 0)].reset_index(drop=True)
    if df.empty:
        raise ValueError("corpus has no usable abstracts to compare the topic against")

    embeddings = embed_texts([state.topic, *df["abstract"].tolist()])
    claim_vec = np.array(embeddings[0])
    corpus_vecs = np.array(embeddings[1:])

    df = df.assign(similarity=[_cosine_sim(claim_vec, v) for v in corpus_vecs])
    nearest = df.sort_values("similarity", ascending=False).head(NEAREST_K)
    overlap_score = float(nearest["similarity"].iloc[0])

    nearest_block = "\n".join(
        f"- {row.title} ({row.year}): similarity={row.similarity:.3f}\n  {str(row.abstract)[:300]}"
        for row in nearest.itertuples()
    )
    system_prompt = build_system_prompt(
        local_suffix="novelty_checker",
        context={
            "topic": state.topic,
            "overlap_score": f"{overlap_score:.3f}",
            "nearest_works": nearest_block,
        },
    )
    verdict, llm_result = call_llm_json(
        [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": "Return the novelty verdict as JSON."},
        ],
        agent_name=AGENT_NAME,
        schema=NoveltyVerdict,
    )

    report_lines = [
        f"# Novelty Report: {state.topic}",
        "",
        f"**Overlap score (max cosine similarity to nearest work):** {overlap_score:.3f}",
        f"**Verdict:** {verdict.verdict}",
        "",
        "## Rationale",
        verdict.rationale,
        "",
        "## 5 Nearest Works",
        *[f"- **{row.title}** ({row.year}) — similarity {row.similarity:.3f}" for row in nearest.itertuples()],
    ]
    relpath = "ideation/novelty_report.md"
    fs_guard.safe_write(state.paper_id, relpath, "\n".join(report_lines), caller_agent=AGENT_NAME)

    return NodeResult(
        update={
            "novelty_verdict": {
                "score": overlap_score,
                "verdict": verdict.verdict,
                "rationale": verdict.rationale,
                "overlapping_works": nearest["title"].tolist(),
            },
            "artifacts": {**state.artifacts, "novelty_report": relpath},
        },
        model=llm_result.model,
        prompt_tokens=llm_result.prompt_tokens,
        completion_tokens=llm_result.completion_tokens,
        cost_usd=llm_result.cost_usd,
        artifacts_written=[relpath],
        output_summary=f"verdict={verdict.verdict} overlap={overlap_score:.3f}",
    )
