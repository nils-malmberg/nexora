"""Date/timezone normalization helpers.

Rule from specs/NEWS_AND_EVENTS.md: unknown dates stay unknown - they are
never silently guessed. Everything is normalized to UTC for storage; the
source timezone (when known) is kept alongside for display.
"""

from __future__ import annotations

from datetime import UTC, datetime
from email.utils import parsedate_to_datetime


def to_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def parse_rfc2822(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return to_utc(parsedate_to_datetime(value))
    except (TypeError, ValueError):
        return None


def parse_iso8601(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        cleaned = value.strip()
        if cleaned.endswith("Z"):
            cleaned = cleaned[:-1] + "+00:00"
        return to_utc(datetime.fromisoformat(cleaned))
    except ValueError:
        return None


def struct_time_to_utc(struct_time) -> datetime | None:
    """feedparser exposes parsed dates as a UTC time.struct_time (or None
    when the source's date string could not be parsed) - never invented."""
    if struct_time is None:
        return None
    import calendar

    return datetime.fromtimestamp(calendar.timegm(struct_time), tz=UTC)
