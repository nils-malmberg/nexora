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


def parse_unix_timestamp(value, unit: str = "seconds") -> datetime | None:
    """Some real JSON APIs (e.g. Finnhub's `CompanyNews.datetime` - see its
    own OpenAPI spec) publish a Unix timestamp instead of ISO 8601. Accepts
    an int/float or a numeric string; never raises on bad input, matching
    the other parse_* helpers here - an unparseable date stays unknown."""
    if value is None or value == "":
        return None
    try:
        seconds = float(value)
    except (TypeError, ValueError):
        return None
    if unit == "milliseconds":
        seconds /= 1000
    try:
        return datetime.fromtimestamp(seconds, tz=UTC)
    except (OverflowError, OSError, ValueError):
        return None


def struct_time_to_utc(struct_time) -> datetime | None:
    """feedparser exposes parsed dates as a UTC time.struct_time (or None
    when the source's date string could not be parsed) - never invented."""
    if struct_time is None:
        return None
    import calendar

    return datetime.fromtimestamp(calendar.timegm(struct_time), tz=UTC)
