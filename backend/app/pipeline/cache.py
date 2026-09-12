"""Freshness / staleness policy.

There is no separate cache layer for V1: persisted rows plus their
`collected_at`/`updated_at` timestamps *are* the cache. `is_stale` is
computed at read time (API layer) against a configurable TTL per data type,
so staleness always reflects the current moment rather than a snapshot that
could itself go stale (see specs/API_SPEC.md: `freshness` field, and
specs/NEWS_AND_EVENTS.md: "signaler cache obsolète").
"""

from __future__ import annotations

from datetime import datetime, timedelta

FreshnessLabel = str  # "realtime" | "delayed" | "estimated" | "unknown"


def snapshot_freshness_label(*, is_estimated: bool, has_known_date: bool) -> FreshnessLabel:
    if is_estimated:
        return "estimated"
    if not has_known_date:
        return "unknown"
    return "delayed"


def is_stale(reference_at: datetime, ttl_minutes: int, now: datetime) -> bool:
    return now - reference_at > timedelta(minutes=ttl_minutes)


def age_seconds(reference_at: datetime, now: datetime) -> float:
    return max(0.0, (now - reference_at).total_seconds())
