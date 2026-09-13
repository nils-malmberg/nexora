"""Explainable relevance scoring.

Deliberately a plain, documented weighted sum - not a model - so every score
can be reconstructed by a human from `relevance_breakdown` alone. This is a
sorting aid, never an investment rating (specs/NEWS_AND_EVENTS.md is explicit
about that distinction).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime

CATEGORY_WEIGHTS = {
    "resultats": 1.0,
    "reglementation": 0.9,
    "operation_titre": 0.9,
    "dividende": 0.8,
    "gouvernance": 0.6,
    "marche": 0.5,
    "macro": 0.4,
    "autre": 0.3,
}

FACTOR_WEIGHTS = {
    "asset_match": 0.25,
    "recency": 0.20,
    "category": 0.15,
    "event_importance": 0.15,
    "provenance_quality": 0.15,
    "corroboration": 0.10,
}

RECENCY_HALF_LIFE_HOURS = 48.0


@dataclass
class ScoreInput:
    asset_match_confidence: float
    category: str
    has_event_at: bool
    provenance_confidence: float
    corroboration_count: int
    reference_at: datetime  # event_at if known, else publication_at
    now: datetime


def _recency_score(reference_at: datetime, now: datetime) -> float:
    hours_elapsed = max(0.0, (now - reference_at).total_seconds() / 3600.0)
    return math.pow(0.5, hours_elapsed / RECENCY_HALF_LIFE_HOURS)


def compute_relevance(inp: ScoreInput) -> tuple[float, dict]:
    subscores = {
        "asset_match": max(0.0, min(1.0, inp.asset_match_confidence)),
        "recency": _recency_score(inp.reference_at, inp.now),
        "category": CATEGORY_WEIGHTS.get(inp.category, CATEGORY_WEIGHTS["autre"]),
        "event_importance": 1.0 if inp.has_event_at else 0.5,
        "provenance_quality": max(0.0, min(1.0, inp.provenance_confidence)),
        "corroboration": min(1.0, inp.corroboration_count / 3.0),
    }
    total = sum(subscores[factor] * weight for factor, weight in FACTOR_WEIGHTS.items())
    breakdown = {
        "weights": FACTOR_WEIGHTS,
        "subscores": subscores,
        "contributions": {f: round(subscores[f] * w, 4) for f, w in FACTOR_WEIGHTS.items()},
        "total": round(total, 4),
    }
    return round(total, 4), breakdown
