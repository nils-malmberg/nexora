"""Adapter interface every provider integration must implement.

Kept deliberately small (`fetch` / `normalize` / `health` / `capabilities`)
so the domain and pipeline never depend on a specific vendor - see
"Architecture et résilience" in specs/NEWS_AND_EVENTS.md. Adapters raise the
typed exceptions below instead of leaking library-specific errors, so the
pipeline can apply one retry/circuit-breaker policy for all of them.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal

ContentType = Literal["news", "event"]


class AdapterError(Exception):
    """Base class for all adapter failures."""


class AdapterTimeout(AdapterError):
    pass


class AdapterRateLimited(AdapterError):
    def __init__(self, message: str, retry_after_seconds: float | None = None):
        super().__init__(message)
        self.retry_after_seconds = retry_after_seconds


class AdapterHTTPError(AdapterError):
    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


class AdapterParseError(AdapterError):
    pass


class AdapterMisconfigured(AdapterError):
    """Raised when required config (e.g. a referenced env var) is missing."""


@dataclass
class RawRecord:
    """A single provider-native record, kept minimal for audit purposes: no
    full article body is retained, only what the source already exposes as
    metadata/excerpt (see "Sources et conformité" in the spec)."""

    external_id: str | None
    title: str
    url: str
    summary: str | None = None
    published_at: datetime | None = None
    event_at: datetime | None = None
    event_period_label: str | None = None
    category_hint: str | None = None
    kind_hint: str = "fact"
    language: str | None = None
    asset_hint: str | None = None
    event_type_hint: str | None = None
    event_status_hint: str | None = None
    amount_hint: float | None = None
    currency_hint: str | None = None
    raw: dict = field(default_factory=dict)


@dataclass
class RawFetchResult:
    items: list[RawRecord]
    fetched_at: datetime
    next_cursor: str | None = None


@dataclass
class NormalizedNewsItem:
    provider_id: str
    kind: str
    category: str
    title: str
    excerpt: str | None
    publication_at: datetime
    event_at: datetime | None
    timezone: str
    url: str
    citation: str | None
    provenance: str
    confidence: float
    language: str | None
    content_hash: str
    # `asset_hint` is either an already-resolved asset id (feed bound 1:1 to
    # one asset) or a raw symbol/keyword string found in the content; final
    # resolution against the Asset table happens in the pipeline, which is
    # the only layer with DB access (see app/pipeline/ingest.py).
    asset_hint: str | None
    asset_match_method: str
    asset_match_confidence: float
    raw_meta: dict


@dataclass
class NormalizedEvent:
    provider_id: str
    type: str
    starts_at: datetime | None
    period_label: str | None
    timezone: str
    status: str
    amount: float | None
    currency: str | None
    source_url: str
    citation: str | None
    content_hash: str
    asset_hint: str | None
    asset_match_method: str
    asset_match_confidence: float


@dataclass
class HealthStatus:
    ok: bool
    checked_at: datetime
    latency_ms: float | None
    message: str


@dataclass
class AdapterCapabilities:
    content_type: ContentType
    supports_incremental_fetch: bool
    supports_pagination: bool
    typical_rate_limit_per_minute: int | None


class ProviderAdapter(ABC):
    """One instance is constructed per `Provider` row; `provider_id` and
    `provider_config` come from that row (config never holds a raw secret,
    only e.g. an env var name - resolved via `resolve_secret`)."""

    def __init__(self, provider_id: str, provider_config: dict):
        self.provider_id = provider_id
        self.provider_config = provider_config

    @property
    @abstractmethod
    def capabilities(self) -> AdapterCapabilities: ...

    @abstractmethod
    def fetch(self, feed_url: str, feed_extra_config: dict, since: datetime | None) -> RawFetchResult:
        """Retrieve raw records from one feed/endpoint. Must raise one of
        the typed AdapterError subclasses on failure rather than a raw
        library exception."""

    @abstractmethod
    def normalize(self, record: RawRecord) -> NormalizedNewsItem | NormalizedEvent:
        """Pure, side-effect-free transform of one raw record."""

    @abstractmethod
    def health(self, feed_url: str, feed_extra_config: dict) -> HealthStatus:
        """Cheap connectivity/config check, independent of a full fetch."""

    def resolve_secret(self, env_var_name: str | None) -> str | None:
        import os

        if not env_var_name:
            return None
        value = os.environ.get(env_var_name)
        if value is None:
            raise AdapterMisconfigured(f"environment variable '{env_var_name}' is not set")
        return value
