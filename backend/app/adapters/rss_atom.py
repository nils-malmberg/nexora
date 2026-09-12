"""Generic RSS/Atom adapter.

Configurable per provider/feed; no vendor is hardcoded. Works against any
feed an issuer, exchange, or media outlet publishes, respecting whatever
excerpt the feed itself provides (never fetches or scrapes the full article
page - see "Sources et conformité" in specs/NEWS_AND_EVENTS.md).
"""

from __future__ import annotations

from datetime import UTC, datetime
from urllib.parse import urlsplit

import feedparser
import httpx

from app.adapters.base import (
    AdapterCapabilities,
    AdapterHTTPError,
    AdapterParseError,
    AdapterRateLimited,
    AdapterTimeout,
    HealthStatus,
    NormalizedNewsItem,
    ProviderAdapter,
    RawFetchResult,
    RawRecord,
)
from app.adapters.common import (
    canonicalize_url,
    compute_content_hash,
    normalize_category,
    normalize_kind,
    normalize_title,
    truncate,
)
from app.utils.timeparse import struct_time_to_utc


class RssAtomAdapter(ProviderAdapter):
    @property
    def capabilities(self) -> AdapterCapabilities:
        return AdapterCapabilities(
            content_type="news",
            supports_incremental_fetch=True,
            supports_pagination=False,
            typical_rate_limit_per_minute=self.provider_config.get("rate_limit_per_minute", 30),
        )

    def _get(self, url: str) -> httpx.Response:
        timeout = self.provider_config.get("timeout_seconds", 10.0)
        headers = {"User-Agent": self.provider_config.get("user_agent", "NeXoraNewsBot/1.0")}
        try:
            response = httpx.get(url, timeout=timeout, headers=headers, follow_redirects=True)
        except httpx.TimeoutException as exc:
            raise AdapterTimeout(f"timeout fetching {url}") from exc
        except httpx.HTTPError as exc:
            raise AdapterHTTPError(f"network error fetching {url}: {exc}") from exc

        if response.status_code == 429:
            retry_after = response.headers.get("Retry-After")
            raise AdapterRateLimited(
                f"rate limited by {url}",
                retry_after_seconds=float(retry_after) if retry_after else None,
            )
        if response.status_code >= 400:
            raise AdapterHTTPError(f"HTTP {response.status_code} fetching {url}", status_code=response.status_code)
        return response

    def fetch(self, feed_url: str, feed_extra_config: dict, since: datetime | None) -> RawFetchResult:
        response = self._get(feed_url)
        parsed = feedparser.parse(response.content)

        if parsed.bozo and not parsed.entries:
            raise AdapterParseError(f"malformed feed at {feed_url}: {parsed.bozo_exception}")

        feed_language = parsed.feed.get("language")
        bound_asset_id = feed_extra_config.get("asset_id")
        fixed_category_hint = feed_extra_config.get("category_hint")

        items: list[RawRecord] = []
        for entry in parsed.entries:
            published_at = struct_time_to_utc(entry.get("published_parsed") or entry.get("updated_parsed"))
            if since is not None and published_at is not None and published_at <= since:
                continue
            items.append(
                RawRecord(
                    external_id=entry.get("id") or entry.get("guid") or entry.get("link"),
                    title=entry.get("title", "").strip(),
                    url=entry.get("link", feed_url),
                    summary=entry.get("summary") or entry.get("description"),
                    published_at=published_at,
                    category_hint=fixed_category_hint or entry.get("category"),
                    kind_hint="fact",
                    language=entry.get("language") or feed_language,
                    asset_hint=bound_asset_id,
                    raw={"guid": entry.get("id"), "link": entry.get("link"), "title": entry.get("title")},
                )
            )
        return RawFetchResult(items=items)

    def normalize(self, record: RawRecord) -> NormalizedNewsItem:
        if record.published_at is None:
            raise AdapterParseError(f"missing publication date for '{record.title}' ({record.url})")
        if not record.title:
            raise AdapterParseError(f"missing title for {record.url}")

        canonical_url = canonicalize_url(record.url)
        title = normalize_title(record.title)
        domain = urlsplit(canonical_url).netloc

        return NormalizedNewsItem(
            provider_id=self.provider_id,
            kind=normalize_kind(record.kind_hint),
            category=normalize_category(record.category_hint),
            title=truncate(title, 500),
            excerpt=truncate(record.summary, 2000),
            publication_at=record.published_at,
            event_at=None,
            timezone="UTC",
            url=canonical_url,
            citation=f"{title} — {domain}",
            provenance=f"RSS/Atom: {domain}",
            confidence=float(self.provider_config.get("base_confidence", 0.7)),
            language=record.language,
            content_hash=compute_content_hash(self.provider_id, canonical_url, title, None),
            asset_hint=record.asset_hint,
            asset_match_confidence=1.0 if record.asset_hint else 0.5,
            raw_meta=record.raw,
        )

    def health(self, feed_url: str, feed_extra_config: dict) -> HealthStatus:
        started = datetime.now()
        try:
            self._get(feed_url)
        except Exception as exc:  # noqa: BLE001 - deliberately broad for a health probe
            return HealthStatus(
                ok=False,
                checked_at=datetime.now(UTC),
                latency_ms=(datetime.now() - started).total_seconds() * 1000,
                message=str(exc),
            )
        return HealthStatus(
            ok=True,
            checked_at=datetime.now(UTC),
            latency_ms=(datetime.now() - started).total_seconds() * 1000,
            message="ok",
        )
