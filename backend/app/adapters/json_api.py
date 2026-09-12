"""Generic, configuration-driven REST/JSON adapter.

No vendor schema is hardcoded: the field mapping (dotted JSON paths),
pagination style, and auth header are all read from `provider_config`, so
any authorized news or calendar API can be plugged in by configuration
alone. Supports either `content_type: news` or `content_type: event`.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlsplit

import httpx

from app.adapters.base import (
    AdapterCapabilities,
    AdapterHTTPError,
    AdapterMisconfigured,
    AdapterParseError,
    AdapterRateLimited,
    AdapterTimeout,
    HealthStatus,
    NormalizedEvent,
    NormalizedNewsItem,
    ProviderAdapter,
    RawFetchResult,
    RawRecord,
)
from app.adapters.common import (
    canonicalize_url,
    compute_content_hash,
    normalize_category,
    normalize_event_status,
    normalize_kind,
    normalize_title,
    truncate,
)
from app.utils.timeparse import parse_iso8601

MAX_PAGES = 20


def get_path(obj: Any, dotted_path: str | None, default: Any = None) -> Any:
    if not dotted_path:
        return default
    current = obj
    for key in dotted_path.split("."):
        if isinstance(current, dict) and key in current:
            current = current[key]
        else:
            return default
    return current


class JsonApiAdapter(ProviderAdapter):
    @property
    def capabilities(self) -> AdapterCapabilities:
        return AdapterCapabilities(
            content_type=self.provider_config.get("content_type", "news"),
            supports_incremental_fetch=True,
            supports_pagination=True,
            typical_rate_limit_per_minute=self.provider_config.get("rate_limit_per_minute", 60),
        )

    def _auth_headers(self) -> dict:
        auth = self.provider_config.get("auth")
        if not auth:
            return {}
        secret = self.resolve_secret(auth.get("env_var"))
        if secret is None:
            return {}
        header = auth.get("header", "Authorization")
        prefix = auth.get("prefix", "")
        return {header: f"{prefix}{secret}"}

    def _get(self, url: str, params: dict) -> dict:
        timeout = self.provider_config.get("timeout_seconds", 10.0)
        try:
            response = httpx.get(url, params=params, headers=self._auth_headers(), timeout=timeout)
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
        try:
            return response.json()
        except ValueError as exc:
            raise AdapterParseError(f"invalid JSON from {url}: {exc}") from exc

    def fetch(self, feed_url: str, feed_extra_config: dict, since: datetime | None) -> RawFetchResult:
        mapping = self.provider_config.get("mapping")
        if not mapping:
            raise AdapterMisconfigured("provider_config.mapping is required for the json_api adapter")

        pagination = self.provider_config.get("pagination", {})
        style = pagination.get("style", "none")
        items_path = pagination.get("items_path")
        base_params = dict(feed_extra_config.get("query_params", {}))
        bound_asset_id = feed_extra_config.get("asset_id")

        items: list[RawRecord] = []
        page = pagination.get("start", 1)
        cursor = None
        for _ in range(MAX_PAGES):
            params = dict(base_params)
            if style == "page":
                params[pagination.get("param", "page")] = page
                if pagination.get("size_param"):
                    params[pagination["size_param"]] = pagination.get("size", 50)
            elif style == "cursor" and cursor:
                params[pagination.get("cursor_param", "cursor")] = cursor

            payload = self._get(feed_url, params)
            raw_items = get_path(payload, items_path, payload if not items_path else [])
            if not isinstance(raw_items, list):
                raise AdapterParseError(f"expected a list of items at '{items_path}' in response from {feed_url}")

            for raw in raw_items:
                published_at = parse_iso8601(get_path(raw, mapping.get("published_at")))
                if since is not None and published_at is not None and published_at <= since:
                    continue
                items.append(
                    RawRecord(
                        external_id=get_path(raw, mapping.get("external_id")),
                        title=str(get_path(raw, mapping.get("title"), "")).strip(),
                        url=get_path(raw, mapping.get("url"), feed_url),
                        summary=get_path(raw, mapping.get("summary")),
                        published_at=published_at,
                        event_at=parse_iso8601(get_path(raw, mapping.get("event_at"))),
                        event_period_label=get_path(raw, mapping.get("event_period_label")),
                        category_hint=get_path(raw, mapping.get("category")),
                        kind_hint=get_path(raw, mapping.get("kind"), "fact"),
                        language=get_path(raw, mapping.get("language")),
                        asset_hint=bound_asset_id or get_path(raw, mapping.get("asset_symbol")),
                        event_type_hint=get_path(raw, mapping.get("event_type")),
                        event_status_hint=get_path(raw, mapping.get("event_status")),
                        amount_hint=get_path(raw, mapping.get("amount")),
                        currency_hint=get_path(raw, mapping.get("currency")),
                        raw={"id": get_path(raw, mapping.get("external_id"))},
                    )
                )

            if not raw_items:
                break
            if style == "page":
                has_more = get_path(payload, pagination.get("has_more_path"))
                if has_more is False:
                    break
                page += 1
            elif style == "cursor":
                cursor = get_path(payload, pagination.get("next_cursor_path"))
                if not cursor:
                    break
            else:
                break

        return RawFetchResult(items=items)

    def normalize(self, record: RawRecord) -> NormalizedNewsItem | NormalizedEvent:
        if not record.title:
            raise AdapterParseError(f"missing title for {record.url}")

        canonical_url = canonicalize_url(record.url)
        title = normalize_title(record.title)
        domain = urlsplit(canonical_url).netloc
        content_type = self.capabilities.content_type

        if content_type == "event":
            if record.event_at is None and not record.event_period_label:
                raise AdapterParseError(f"missing event date/period for '{title}'")
            return NormalizedEvent(
                provider_id=self.provider_id,
                type=record.event_type_hint or "autre",
                starts_at=record.event_at,
                period_label=record.event_period_label,
                timezone="UTC",
                status=normalize_event_status(record.event_status_hint),
                amount=record.amount_hint,
                currency=record.currency_hint,
                source_url=canonical_url,
                citation=f"{title} — {domain}",
                content_hash=compute_content_hash(self.provider_id, canonical_url, title, record.event_at),
                asset_hint=record.asset_hint,
                asset_match_confidence=1.0 if record.asset_hint else 0.0,
            )

        if record.published_at is None:
            raise AdapterParseError(f"missing publication date for '{title}' ({record.url})")

        return NormalizedNewsItem(
            provider_id=self.provider_id,
            kind=normalize_kind(record.kind_hint),
            category=normalize_category(record.category_hint),
            title=truncate(title, 500),
            excerpt=truncate(record.summary, 2000),
            publication_at=record.published_at,
            event_at=record.event_at,
            timezone="UTC",
            url=canonical_url,
            citation=f"{title} — {domain}",
            provenance=f"API JSON: {domain}",
            confidence=float(self.provider_config.get("base_confidence", 0.6)),
            language=record.language,
            content_hash=compute_content_hash(self.provider_id, canonical_url, title, record.event_at),
            asset_hint=record.asset_hint,
            asset_match_confidence=1.0 if record.asset_hint else 0.5,
            raw_meta=record.raw,
        )

    def health(self, feed_url: str, feed_extra_config: dict) -> HealthStatus:
        started = datetime.now()
        try:
            self._get(feed_url, dict(feed_extra_config.get("query_params", {})))
        except Exception as exc:  # noqa: BLE001
            return HealthStatus(ok=False, checked_at=datetime.now(UTC), latency_ms=None, message=str(exc))
        return HealthStatus(
            ok=True,
            checked_at=datetime.now(UTC),
            latency_ms=(datetime.now() - started).total_seconds() * 1000,
            message="ok",
        )
