"""Read-only dashboard API over papers/<slug>/ workspaces.

No write endpoints in v1 -- see the plan this was built from. Every route reads
files/checkpoint state that already exists on disk; nothing here mutates a
paper's state. Run with:

    uvicorn web.backend.app:app --reload --port 8000
"""

from __future__ import annotations

import json

import yaml
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from engine.config import PAPERS_ROOT, checkpoint_path, paper_dir
from engine.provenance import ProvenanceEntry, read_provenance, summarize_usage, total_usage
from engine.tools import fs_guard
from web.backend.flow_status import compute_flow_status
from web.backend.schemas import FlowStatus, PaperDetail, PaperSummary

app = FastAPI(title="research-pipeline dashboard")

# Vite dev server runs on a different port; this is a local single-user tool, so a
# permissive dev CORS policy is fine (no auth, nothing sensitive beyond what's
# already readable from the filesystem this process runs in).
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["GET"],
    allow_headers=["*"],
)


def _load_paper_yaml_or_404(paper_id: str) -> dict:
    path = paper_dir(paper_id) / "paper.yaml"
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"papers/{paper_id}/paper.yaml not found")
    return yaml.safe_load(path.read_text())


def _load_live_state(paper_id: str) -> dict | None:
    """Best-effort read of the LangGraph checkpoint's current state, if a run
    has ever happened. Returns None (not an error) for a paper that's only
    been scaffolded via `engine new` and never run.
    """
    db_path = checkpoint_path(paper_id)
    if not db_path.exists():
        return None

    from langgraph.checkpoint.sqlite import SqliteSaver

    from engine.graphs.master import build_master_graph

    with SqliteSaver.from_conn_string(str(db_path)) as checkpointer:
        graph = build_master_graph().compile(checkpointer=checkpointer)
        snapshot = graph.get_state({"configurable": {"thread_id": paper_id}})
        return dict(snapshot.values) if snapshot and snapshot.values else None


@app.get("/api/papers", response_model=list[PaperSummary])
def list_papers() -> list[PaperSummary]:
    if not PAPERS_ROOT.exists():
        return []
    summaries = []
    for yaml_path in sorted(PAPERS_ROOT.glob("*/paper.yaml")):
        doc = yaml.safe_load(yaml_path.read_text())
        summaries.append(
            PaperSummary(
                paper_id=doc["paper_id"],
                topic=doc.get("topic", ""),
                venue=doc.get("venue"),
                phase=doc.get("phase", "ideation"),
                status=doc.get("status", "new"),
            )
        )
    return summaries


@app.get("/api/papers/{paper_id}", response_model=PaperDetail)
def get_paper(paper_id: str) -> PaperDetail:
    doc = _load_paper_yaml_or_404(paper_id)
    live = _load_live_state(paper_id)

    input_needed_path = paper_dir(paper_id) / "HUMAN_INPUT_NEEDED.json"
    gate_payload = json.loads(input_needed_path.read_text()) if input_needed_path.exists() else None

    return PaperDetail(
        paper_id=paper_id,
        topic=(live or {}).get("topic", doc.get("topic", "")),
        venue=(live or {}).get("venue", doc.get("venue")),
        phase=(live or {}).get("phase", doc.get("phase", "ideation")),
        status=doc.get("status", "new"),
        revision_loop_count=(live or {}).get("revision_loop_count", 0),
        errors=(live or {}).get("errors", []),
        artifacts=(live or {}).get("artifacts", {}),
        paused=gate_payload is not None,
        gate_payload=gate_payload,
    )


@app.get("/api/papers/{paper_id}/flow", response_model=FlowStatus)
def get_flow(paper_id: str) -> FlowStatus:
    _load_paper_yaml_or_404(paper_id)
    return compute_flow_status(paper_id)


@app.get("/api/papers/{paper_id}/provenance", response_model=list[ProvenanceEntry])
def get_provenance(paper_id: str) -> list[ProvenanceEntry]:
    _load_paper_yaml_or_404(paper_id)
    return read_provenance(paper_id)


@app.get("/api/papers/{paper_id}/costs")
def get_costs(paper_id: str, by_model: bool = False) -> dict:
    _load_paper_yaml_or_404(paper_id)
    entries = read_provenance(paper_id)
    rows = summarize_usage(entries, by_model=by_model)
    return {"rows": [r.model_dump() for r in rows], "total": total_usage(entries).model_dump()}


@app.get("/api/papers/{paper_id}/artifacts/{artifact_path:path}")
def get_artifact(paper_id: str, artifact_path: str) -> dict:
    _load_paper_yaml_or_404(paper_id)
    try:
        resolved = fs_guard.resolve_path(paper_id, artifact_path)
    except fs_guard.ArtifactWriteError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not resolved.exists() or not resolved.is_file():
        raise HTTPException(status_code=404, detail=f"{artifact_path} not found")
    return {"path": artifact_path, "content": resolved.read_text(errors="replace")}
