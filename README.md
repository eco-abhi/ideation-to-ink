# research-pipeline

A LangGraph-based multi-agent pipeline that takes a research paper from
**ideation → experiment design → drafting → adversarial pre-review → revision**,
producing a submission-ready LaTeX manuscript with verified citations only and a
full provenance log of every agent action.

Built for a single power user. Optimized for reliability, resumability, and
auditability over cleverness.

## Quickstart

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env   # fill in ANTHROPIC_API_KEY (or another litellm-supported model) + EMBEDDING_MODEL key

python -m engine new my-paper --topic "LLM agents for supply chain exception handling"
python -m engine run my-paper
```

`run` executes until it either finishes a phase transition or hits a
human-in-the-loop gate, at which point it writes
`papers/my-paper/HUMAN_INPUT_NEEDED.json` describing what it needs and exits.
Write your decision to `papers/my-paper/HUMAN_RESPONSE.json` (the file
describes the expected shape, e.g. `{"decision": "proceed"}`) and rerun with
`--resume`. Kill the process at any point — a checkpoint is persisted after
every node, so `--resume` (or even a bare `run` again, if you weren't mid-gate)
continues from exactly where it left off.

## CLI

- `engine new <slug> --topic "..."` — scaffold `papers/<slug>/`
- `engine run <slug> [--phase X] [--resume]` — run or resume the pipeline
- `engine import <slug> --from <dir>` — ingest an existing draft (`.tex`/`.bib`;
  `.md`/`.docx` copied verbatim, not parsed), backfill state, and run the
  retroactive citation/claims/flow gates against `reviews/round_00/`
- `engine check <slug> --agent <name>` — run one agent standalone against the
  current workspace without a full pipeline run. Available:
  `review_ensemble`, `citation_verifier`, `redline_diff`, `rebuttal_writer`,
  `state_compaction`
- `engine costs <slug> [--by-model]` — token usage and cost, aggregated from
  `provenance/run_log.jsonl`

## Dashboard

A web dashboard over `papers/<slug>/` workspaces -- create a paper, run it, and
respond to every gate without touching the CLI: paper list with a "New paper"
form, a live process-flow diagram (colored by node status:
pending/completed/failed/paused, click a node for its provenance detail or the
paused gate's payload with one-click response actions), and the same
cost/usage data `engine costs` prints, rendered as a table.

```bash
pip install -e ".[dev,web]"
uvicorn web.backend.app:app --reload --port 8000      # terminal 1

cd web/frontend && npm install                        # first time only
npm run dev                                            # terminal 2, http://localhost:5173
```

`POST /api/papers/{slug}/run` runs `run_paper()` in a background thread (in-
memory tracking, resets on backend restart -- fine for a local dev tool; a
second concurrent run against the same paper is rejected with 409) so the
request returns immediately and the UI polls for progress. Gate responses
(`POST /api/papers/{slug}/respond`) write `HUMAN_RESPONSE.json` -- the same
file the CLI's `--resume` flow reads -- and trigger a resume run the same way;
`GatePanel.tsx` renders one-click buttons per gate type (Proceed/Stop,
Approve/Revise, etc.) instead of you hand-writing that JSON. Still no
WebSocket: every route reads/writes exactly the files `engine run` already
uses, so the CLI and the dashboard interoperate freely -- drive a paper from
either at any point. See `web/backend/topology.py`'s docstring for how the
flow diagram's node/edge structure is derived (hand-authored, guarded against
drift from the real graph by `tests/test_topology.py`).

## Architecture

```
engine/
├── graphs/       ideation.py, experiments.py, writing.py, review.py, master.py
├── agents/       one file per agent (node functions)
├── state.py      PaperState — the single shared contract
├── prompts/
│   ├── vendored/ re-paper-writing skills (read-only, upstream-tracked)
│   └── local/    project-specific suffixes + skills authored in-house
├── tools/        openalex.py, semanticscholar.py, arxiv.py, crossref.py, ...
├── llm.py        provider-agnostic model wrapper (LiteLLM) + logging
├── provenance.py append-only JSONL run logger
└── checkpoints/  sqlite DBs (gitignored)

papers/<slug>/    one workspace per paper (see paper.yaml, ideation/,
                  experiments/, manuscript/, reviews/, provenance/)
shared/venues/    per-venue review criteria, page limits, reviewer personas
```

Every phase module (`graphs/ideation.py`, `experiments.py`, `writing.py`,
`review.py`) exposes an `add_*_nodes(builder)` function that registers its
nodes onto a **shared** `StateGraph`, rather than nested compiled subgraphs.
This is deliberate: the review phase's revision loop needs to jump back into
`section_drafters`, a node the writing phase owns, and LangGraph subgraphs
can't reach into another subgraph's internal nodes. `graphs/master.py` is the
only place that knows the full cross-phase topology and wires it in the spec's
true order (ideation → experiments → writing → review), with a conditional
entry point keyed on `PaperState.phase` so a resumed run re-enters the right
phase — including `"revision"`, which resumes at `section_drafters` rather than
regenerating a fresh outline.

### Guardrails (enforced in code, not convention)

- **`refs.bib` is writable only by `citation_verifier`** — checked in
  `engine/tools/fs_guard.py`'s `ARTIFACT_WRITE_POLICY` at write time, not
  documented-and-hoped-for.
- **No agent writes outside `papers/<paper_id>/`** — `fs_guard.safe_write`
  resolves every path and rejects anything that escapes the paper root.
- **LaTeX/BibTeX writes reject shell-escape constructs** (`\write18`,
  absolute-path `\input`/`\include`, active-char redefinition) before hitting
  disk, since LLM-authored `.tex` is eventually fed to `pdflatex`.
  `fs_guard.latex_escape` is available for interpolating plain-text strings
  (API-sourced titles, etc.) into `.tex`/`.bib` without mangling legitimate
  LaTeX commands.
- **No node runs unlogged, and a node failure never silently continues.**
  `graphs/_registry.traced_node` is the only way a node function gets
  registered — it wraps every call with provenance logging
  (`papers/<slug>/provenance/run_log.jsonl`: agent, model, skill + upstream
  commit, tokens, artifacts written, duration) and, on exception, routes to a
  shared `error_gate` that appends to `state.errors` and interrupts for human
  review instead of crashing the process or plowing ahead.
- **Every external API call is cached to disk** (`engine/tools/cache.py`), so
  a rerun with a warm cache needs no network access.

### Citation verification cascade

`section_drafters` proposes citations into an **untrusted**
`manuscript/refs_draft.bib` — exactly as trustworthy as anything else an LLM
generates. `citation_verifier` is the only agent that reads it and the only
one allowed to write the real `manuscript/refs.bib`, via:

- **L1**: arXiv ID lookup
- **L2**: CrossRef DOI resolution
- **L3**: title search (Semantic Scholar + arXiv), title-similarity threshold

Every entry is classified `verified` / `suspicious` / `hallucinated` /
`skipped`; `verified` entries get one more LLM pass checking the matched
abstract actually supports the claim it's attached to (not just topical
overlap). Only `verified` entries land in `refs.bib` automatically;
`suspicious` entries pause the graph for a human decision
(`citation_human_gate` in `graphs/writing.py`); `hallucinated`/`skipped`
entries have their `\cite{}` occurrences stripped from every section file, and
any claim left with zero surviving citations is marked `disputed`.

### Provider-agnostic LLM access

`engine/llm.py` wraps [LiteLLM](https://docs.litellm.ai), so switching models
is a `.env` change (`DEFAULT_LLM_MODEL`, optional per-agent
`AGENT_MODEL_OVERRIDES`), never a code change. `litellm.drop_params = True` is
set deliberately — some models (reasoning models in particular) reject
parameters like an explicit `temperature`; rather than special-case models
here, unsupported params are dropped instead of hard-failing the call.
`novelty_checker`'s embedding step uses a separate `EMBEDDING_MODEL`, since a
chat-only model won't necessarily support embeddings.

## Known scope cuts

Documented here rather than silently shipped as if complete:

- **`experiment-report-bridge`** is loaded by `stats_validator`, not
  `experiment_scaffolder` as the original spec listed — that skill turns
  *finished* results into a manuscript handoff, which can't happen before
  scaffolding runs and results exist.
- **`paper-redline-diff`** and **`rebuttal-writing`** are standalone
  `engine check`-invokable agents (`redline_diff`, `rebuttal_writer`), not
  steps inside the automated `revision_router` loop — there's nothing to diff
  against before a redraft exists, and rebuttals are a post-submission,
  human-facing concern outside the automated pre-review loop.
- **`engine import`** parses `.tex` and `.bib` only. `.md`/`.docx` files under
  `--from` are copied verbatim into `imported_source/` rather than parsed —
  real DOCX parsing would need an additional dependency this build doesn't
  include. It also doesn't attempt to split a monolithic `main.tex` into
  logical sections; every `.tex` file found becomes one section, keyed by
  filename.
- **State compaction** (`state_compaction` agent) writes a human-readable
  summary ledger; it does not actually shrink `PaperState`'s accumulating
  fields. LangGraph's `operator.add` reducer on `claims`/`citation_records`/
  `review_rounds` is append-only from any single node's return value, so a
  node can't truncate those fields in place. `PaperState.effective_*()`
  methods keep the *logical* (deduped, last-write-wins) view bounded, which is
  what matters for correctness; the ledger is about not having to replay the
  full history, not memory reclamation.
- **`engine import`'s title/topic inference** only looks for a `\title{}`
  command in the first `.tex` file that has one; falls back to the slug.

## What's verified vs. what needs your credentials

Everything except live network calls and `pdflatex` is verified by the test
suite (`pytest -q`) with every LLM/API call mocked — citation classification
logic, the revision loop (including hitting the 3-loop cap and the human
override), kill-and-resume via a real sqlite checkpointer, the retroactive
import gates catching a seeded fake citation, and a full pipeline run through
every phase to `phase=done`.

Not independently run this session (need your `.env` filled in, and for
criterion 4, a LaTeX toolchain):

- A real `literature_scout` corpus pull (≥100 deduped works)
- A real `pdflatex` compile of the generated manuscript
- A real 3-reviewer LLM ensemble converging on an actual draft

Run `engine run <slug>` yourself once `.env` has real credentials to exercise
those for real.

## Tests & lint

```bash
pytest -q
ruff check .
```
