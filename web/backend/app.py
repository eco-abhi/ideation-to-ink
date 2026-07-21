"""Dashboard API over papers/<slug>/ workspaces.

v1 was read-only; this adds the write surface needed to drive the pipeline
entirely from the UI: create a paper, trigger a run, respond to a paused gate.
Every write still goes through the exact same engine entry points the CLI
uses (scaffold_workspace, run_paper) -- this is a thin HTTP wrapper, not a
second implementation of pipeline logic. Run with:

    uvicorn web.backend.app:app --reload --port 8000
"""

from __future__ import annotations

import json
import re
import threading

import yaml
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from engine.config import PAPERS_ROOT, checkpoint_path, paper_dir
from engine.provenance import ProvenanceEntry, read_provenance, summarize_usage, total_usage
from engine.tools import fs_guard
from engine.tools.workspace import scaffold_workspace
from web.backend.flow_status import compute_flow_status
from web.backend.schemas import FlowStatus, PaperDetail, PaperSummary

app = FastAPI(title="research-pipeline dashboard")

# Vite dev server runs on a different port; this is a local single-user tool, so a
# permissive dev CORS policy is fine (no auth, nothing sensitive beyond what's
# already readable/writable from the filesystem this process runs in).
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

_SLUG_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_-]*$")

# In-memory only -- resets on backend restart, which is fine for a local dev
# tool. Tracks which papers have a run_paper() call executing in a background
# thread right now, so the UI can show "running" and the API can refuse to
# start a second concurrent run against the same checkpoint.
_running_lock = threading.Lock()
_running: set[str] = set()


def _validate_slug(slug: str) -> None:
    if not _SLUG_RE.match(slug):
        raise HTTPException(status_code=400, detail="slug must start with alphanumeric, then alphanumeric/-/_ only")


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


def _run_in_background(paper_id: str, *, target_phase: str | None, resume: bool) -> None:
    from engine.graphs.master import run_paper

    try:
        run_paper(paper_id, target_phase=target_phase, resume=resume)
    finally:
        with _running_lock:
            _running.discard(paper_id)


def _start_run(paper_id: str, *, target_phase: str | None, resume: bool) -> None:
    with _running_lock:
        if paper_id in _running:
            raise HTTPException(status_code=409, detail=f"a run is already in progress for {paper_id!r}")
        _running.add(paper_id)
    thread = threading.Thread(
        target=_run_in_background, args=(paper_id,), kwargs={"target_phase": target_phase, "resume": resume}, daemon=True
    )
    thread.start()


def _paper_summary_kwargs(doc: dict, live: dict | None = None) -> dict:
    live = live or {}
    return {
        "title": live.get("topic", doc.get("topic", "")),
        "keywords": live.get("keywords", doc.get("keywords", [])),
        "abstract": live.get("abstract", doc.get("abstract")),
        "venue": live.get("venue", doc.get("venue")),
        "phase": live.get("phase", doc.get("phase", "ideation")),
        "status": doc.get("status", "new"),
    }


@app.get("/api/papers", response_model=list[PaperSummary])
def list_papers() -> list[PaperSummary]:
    if not PAPERS_ROOT.exists():
        return []
    summaries = []
    for yaml_path in sorted(PAPERS_ROOT.glob("*/paper.yaml")):
        doc = yaml.safe_load(yaml_path.read_text())
        summaries.append(PaperSummary(paper_id=doc["paper_id"], **_paper_summary_kwargs(doc)))
    return summaries


class CreatePaperRequest(BaseModel):
    slug: str
    title: str
    keywords: list[str] = []
    abstract: str | None = None


MAX_TITLE_LENGTH = 300  # title doubles as a literal literature-search query -- see literature_scout.py


@app.post("/api/papers", response_model=PaperSummary, status_code=201)
def create_paper(req: CreatePaperRequest) -> PaperSummary:
    _validate_slug(req.slug)
    title = req.title.strip()
    if not title:
        raise HTTPException(status_code=400, detail="title must not be empty")
    if len(title) > MAX_TITLE_LENGTH:
        raise HTTPException(
            status_code=400,
            detail=f"title must be under {MAX_TITLE_LENGTH} characters -- it's used as a literal search query "
            "against literature APIs, not a place for the full abstract (use the Abstract field for that)",
        )
    try:
        scaffold_workspace(req.slug, topic=title, keywords=req.keywords, abstract=req.abstract)
    except FileExistsError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    doc = _load_paper_yaml_or_404(req.slug)
    return PaperSummary(paper_id=req.slug, **_paper_summary_kwargs(doc))


@app.get("/api/papers/{paper_id}", response_model=PaperDetail)
def get_paper(paper_id: str) -> PaperDetail:
    doc = _load_paper_yaml_or_404(paper_id)
    live = _load_live_state(paper_id)

    input_needed_path = paper_dir(paper_id) / "HUMAN_INPUT_NEEDED.json"
    gate_payload = json.loads(input_needed_path.read_text()) if input_needed_path.exists() else None

    with _running_lock:
        running = paper_id in _running

    return PaperDetail(
        paper_id=paper_id,
        **_paper_summary_kwargs(doc, live),
        revision_loop_count=(live or {}).get("revision_loop_count", 0),
        errors=(live or {}).get("errors", []),
        artifacts=(live or {}).get("artifacts", {}),
        paused=gate_payload is not None and not running,
        gate_payload=gate_payload if not running else None,
        running=running,
    )


class RunRequest(BaseModel):
    phase: str | None = None


@app.post("/api/papers/{paper_id}/run", status_code=202)
def trigger_run(paper_id: str, req: RunRequest | None = None) -> dict:
    _load_paper_yaml_or_404(paper_id)
    _start_run(paper_id, target_phase=req.phase if req else None, resume=False)
    return {"status": "started"}


@app.post("/api/papers/{paper_id}/respond", status_code=202)
def respond_to_gate(paper_id: str, response: dict) -> dict:
    """Writes HUMAN_RESPONSE.json (same file/shape the CLI's --resume flow
    reads) and immediately triggers a background --resume run. `response` must
    be a non-empty JSON object -- see engine/graphs/master.py's run_paper()
    docstring-level comment about why an empty dict or null breaks LangGraph's
    Command(resume=...) in the pinned version.
    """
    _load_paper_yaml_or_404(paper_id)
    if not response:
        raise HTTPException(status_code=400, detail="response body must be a non-empty JSON object")
    response_path = paper_dir(paper_id) / "HUMAN_RESPONSE.json"
    response_path.write_text(json.dumps(response))
    _start_run(paper_id, target_phase=None, resume=True)
    return {"status": "resuming"}


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
