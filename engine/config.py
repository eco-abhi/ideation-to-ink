"""Environment-driven configuration. No secrets or model names hardcoded elsewhere."""

from __future__ import annotations

import json
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

REPO_ROOT = Path(__file__).resolve().parent.parent
PAPERS_ROOT = REPO_ROOT / "papers"
SHARED_ROOT = REPO_ROOT / "shared"
CHECKPOINTS_ROOT = REPO_ROOT / "engine" / "checkpoints"
CACHE_ROOT = REPO_ROOT / "engine" / ".cache"

DEFAULT_LLM_MODEL = os.environ.get("DEFAULT_LLM_MODEL", "anthropic/claude-sonnet-5")
EMBEDDING_MODEL = os.environ.get("EMBEDDING_MODEL", "openai/text-embedding-3-small")

_overrides_raw = os.environ.get("AGENT_MODEL_OVERRIDES", "")
AGENT_MODEL_OVERRIDES: dict[str, str] = json.loads(_overrides_raw) if _overrides_raw else {}

SEMANTIC_SCHOLAR_API_KEY = os.environ.get("SEMANTIC_SCHOLAR_API_KEY") or None
CROSSREF_CONTACT_EMAIL = os.environ.get("CROSSREF_CONTACT_EMAIL") or None

LITERATURE_CACHE_TTL_DAYS = int(os.environ.get("LITERATURE_CACHE_TTL_DAYS", "30"))

MAX_REVISION_LOOPS = 3


def model_for_agent(agent_name: str) -> str:
    return AGENT_MODEL_OVERRIDES.get(agent_name, DEFAULT_LLM_MODEL)


def paper_dir(paper_id: str) -> Path:
    return PAPERS_ROOT / paper_id


def checkpoint_path(paper_id: str) -> Path:
    CHECKPOINTS_ROOT.mkdir(parents=True, exist_ok=True)
    return CHECKPOINTS_ROOT / f"{paper_id}.sqlite"
