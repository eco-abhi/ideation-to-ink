"""Loads shared/venues/*.yaml -- the venue configs every writing/review-phase
agent (venue_strategist, adversarial_reviewer_ensemble, compliance_checker) reads.
"""

from __future__ import annotations

from functools import lru_cache

import yaml

from engine.config import SHARED_ROOT

VENUES_DIR = SHARED_ROOT / "venues"


@lru_cache(maxsize=1)
def list_venues() -> list[dict]:
    return [yaml.safe_load(path.read_text()) for path in sorted(VENUES_DIR.glob("*.yaml"))]


def get_venue(slug: str) -> dict | None:
    return next((v for v in list_venues() if v.get("slug") == slug), None)
