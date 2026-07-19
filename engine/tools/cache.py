"""Generic on-disk JSON cache shared by every literature API client.

Guardrail: "every external API call cached to disk; pipeline must be re-runnable
offline from cache." As long as a fresh cache entry exists, `cached_get` never
calls `fetch`, so a warm cache makes a rerun fully offline.
"""

from __future__ import annotations

import hashlib
import json
import time
from collections.abc import Callable
from typing import Any

from engine.config import CACHE_ROOT, LITERATURE_CACHE_TTL_DAYS


def _cache_key(endpoint: str, params: dict[str, Any]) -> str:
    blob = json.dumps({"endpoint": endpoint, "params": params}, sort_keys=True, default=str)
    return hashlib.sha256(blob.encode()).hexdigest()


def cached_get(
    source: str,
    endpoint: str,
    params: dict[str, Any],
    fetch: Callable[[], Any],
    *,
    ttl_days: float | None = None,
) -> Any:
    ttl = LITERATURE_CACHE_TTL_DAYS if ttl_days is None else ttl_days
    path = CACHE_ROOT / source / f"{_cache_key(endpoint, params)}.json"

    if path.exists():
        age_days = (time.time() - path.stat().st_mtime) / 86400
        if age_days <= ttl:
            return json.loads(path.read_text())

    result = fetch()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result))
    return result
