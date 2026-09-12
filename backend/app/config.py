"""Application configuration.

All values are read from environment variables (or a local `.env` file that
is never committed). No secret, key, or credential is ever hardcoded here —
see specs/SECURITY.md. Provider adapters store only the *name* of the
environment variable holding a credential, never the credential itself.
"""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="NEXORA_", extra="ignore")

    # Defaults to a local SQLite file so the module runs with zero external
    # services for development/tests. Production points this at Postgres
    # (see docker-compose.yml and ARCHITECTURE.md).
    database_url: str = "sqlite:///./nexora_news_events.db"

    # Static admin key gating the protected sync-trigger endpoints. This is a
    # placeholder until the module is wired into the dashboard's real auth
    # (OIDC/session) — see specs/SECURITY.md. Must be overridden in any
    # non-local environment; a missing/empty value disables admin endpoints.
    admin_api_key: str = ""

    # Freshness targets (minutes) used to compute the `stale` flag on API
    # responses and freshness metrics/alerts. Configurable per data type.
    news_freshness_minutes: int = 60
    event_freshness_minutes: int = 24 * 60

    # Ingestion scheduling & resilience.
    ingestion_interval_seconds: int = 15 * 60
    ingestion_jitter_seconds: int = 60
    http_timeout_seconds: float = 10.0
    max_retries: int = 3
    retry_backoff_base_seconds: float = 1.0
    circuit_breaker_failure_threshold: int = 5
    circuit_breaker_reset_seconds: int = 300

    # Pagination limits.
    default_page_size: int = 20
    max_page_size: int = 100

    # Dedup similarity threshold (0-1) for near-duplicate title matching
    # within the same asset and a bounded time window.
    dedup_title_similarity_threshold: float = 0.88
    dedup_time_window_hours: int = 72

    log_level: str = "INFO"
    environment: str = "development"

    # Comma-separated list of allowed origins for the (cookie-less, read-only)
    # API. "*" is safe here since no credentialed/cookie-based request is
    # ever made against this API - see specs/SECURITY.md.
    cors_allowed_origins: str = "*"

    # The worker is a separate process from the API with its own in-memory
    # Prometheus registry, so it exposes its own /metrics on this port
    # rather than sharing the API's (see app/worker/scheduler.py).
    worker_metrics_port: int = 9100


settings = Settings()
