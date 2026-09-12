"""Official calendar adapter (iCalendar / ICS), as published by many issuers
and exchanges for results, dividends, AGMs, maturities, etc.

Non-standard fields (event type, amount/currency, asset symbol when a feed
is not already bound to one asset) are read from `X-NEXORA-*` custom
properties when present; anything not published is left `None` rather than
guessed. All-day entries (date only, no time) keep the date as
`period_label` instead of inventing a time-of-day.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from urllib.parse import urlsplit

import httpx
from icalendar import Calendar

from app.adapters.base import (
    AdapterCapabilities,
    AdapterHTTPError,
    AdapterParseError,
    AdapterRateLimited,
    AdapterTimeout,
    HealthStatus,
    NormalizedEvent,
    ProviderAdapter,
    RawFetchResult,
    RawRecord,
)
from app.adapters.common import canonicalize_url, compute_content_hash, normalize_event_status, normalize_title
from app.utils.timeparse import to_utc

_STATUS_MAP = {"CONFIRMED": "confirme", "TENTATIVE": "previsionnel", "CANCELLED": "annule"}


def _prop(component, name: str) -> str | None:
    value = component.get(name)
    return str(value) if value else None


class CalendarIcsAdapter(ProviderAdapter):
    @property
    def capabilities(self) -> AdapterCapabilities:
        return AdapterCapabilities(
            content_type="event",
            supports_incremental_fetch=False,
            supports_pagination=False,
            typical_rate_limit_per_minute=self.provider_config.get("rate_limit_per_minute", 30),
        )

    def _get(self, url: str) -> bytes:
        timeout = self.provider_config.get("timeout_seconds", 10.0)
        try:
            response = httpx.get(url, timeout=timeout, follow_redirects=True)
        except httpx.TimeoutException as exc:
            raise AdapterTimeout(f"timeout fetching {url}") from exc
        except httpx.HTTPError as exc:
            raise AdapterHTTPError(f"network error fetching {url}: {exc}") from exc

        if response.status_code == 429:
            retry_after = response.headers.get("Retry-After")
            raise AdapterRateLimited(
                f"rate limited by {url}", retry_after_seconds=float(retry_after) if retry_after else None
            )
        if response.status_code >= 400:
            raise AdapterHTTPError(f"HTTP {response.status_code} fetching {url}", status_code=response.status_code)
        return response.content

    def fetch(self, feed_url: str, feed_extra_config: dict, since: datetime | None) -> RawFetchResult:
        content = self._get(feed_url)
        try:
            calendar = Calendar.from_ical(content)
        except ValueError as exc:
            raise AdapterParseError(f"malformed ICS calendar at {feed_url}: {exc}") from exc

        bound_asset_id = feed_extra_config.get("asset_id")
        items: list[RawRecord] = []
        for component in calendar.walk("VEVENT"):
            dtstart = component.get("dtstart")
            event_at: datetime | None = None
            period_label: str | None = None
            if dtstart is not None:
                value = dtstart.dt
                if isinstance(value, datetime):
                    event_at = to_utc(value) if value.tzinfo else value.replace(tzinfo=UTC)
                elif isinstance(value, date):
                    period_label = value.isoformat()

            if since is not None and event_at is not None and event_at <= since:
                continue

            amount_raw = _prop(component, "x-nexora-amount")
            uid = _prop(component, "uid")
            items.append(
                RawRecord(
                    external_id=uid,
                    title=str(component.get("summary", "")).strip(),
                    url=_prop(component, "url") or feed_url,
                    summary=_prop(component, "description"),
                    event_at=event_at,
                    event_period_label=period_label,
                    event_type_hint=_prop(component, "x-nexora-event-type"),
                    event_status_hint=_prop(component, "status"),
                    amount_hint=float(amount_raw) if amount_raw else None,
                    currency_hint=_prop(component, "x-nexora-currency"),
                    asset_hint=bound_asset_id or _prop(component, "x-nexora-asset-symbol"),
                    raw={"uid": uid},
                )
            )
        return RawFetchResult(items=items)

    def normalize(self, record: RawRecord) -> NormalizedEvent:
        if not record.title:
            raise AdapterParseError(f"missing SUMMARY for event at {record.url}")
        if record.event_at is None and not record.event_period_label:
            raise AdapterParseError(f"missing DTSTART for event '{record.title}'")

        canonical_url = canonicalize_url(record.url)
        title = normalize_title(record.title)
        domain = urlsplit(canonical_url).netloc

        raw_status = record.event_status_hint
        mapped_status = _STATUS_MAP.get((raw_status or "").upper()) if raw_status else None
        status = normalize_event_status(mapped_status or raw_status)

        return NormalizedEvent(
            provider_id=self.provider_id,
            type=record.event_type_hint or "autre",
            starts_at=record.event_at,
            period_label=record.event_period_label,
            timezone="UTC",
            status=status,
            amount=record.amount_hint,
            currency=record.currency_hint,
            source_url=canonical_url,
            citation=f"{title} — {domain}",
            content_hash=compute_content_hash(self.provider_id, canonical_url, title, record.event_at),
            asset_hint=record.asset_hint,
            asset_match_confidence=1.0 if record.asset_hint else 0.0,
        )

    def health(self, feed_url: str, feed_extra_config: dict) -> HealthStatus:
        started = datetime.now()
        try:
            self._get(feed_url)
        except Exception as exc:  # noqa: BLE001
            return HealthStatus(ok=False, checked_at=datetime.now(UTC), latency_ms=None, message=str(exc))
        return HealthStatus(
            ok=True,
            checked_at=datetime.now(UTC),
            latency_ms=(datetime.now() - started).total_seconds() * 1000,
            message="ok",
        )
