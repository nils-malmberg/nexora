from __future__ import annotations

from datetime import datetime

GRANULARITIES = {"day", "month", "quarter", "year"}


def bucket_label(dt: datetime | None, granularity: str) -> str:
    if granularity not in GRANULARITIES:
        raise ValueError(f"unknown granularity '{granularity}'")
    if dt is None:
        return "unknown"
    if granularity == "day":
        return dt.strftime("%Y-%m-%d")
    if granularity == "month":
        return dt.strftime("%Y-%m")
    if granularity == "year":
        return dt.strftime("%Y")
    quarter = (dt.month - 1) // 3 + 1
    return f"{dt.year}-Q{quarter}"
