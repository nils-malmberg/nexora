"""Application configuration — one `Settings` for the whole application.

All values are read from environment variables (prefix `NEXORA_`) or a local
`.env` file that is never committed. No secret, key, or credential is ever
hardcoded here — see specs/SECURITY.md. Market/news adapters store only the
*name* of the environment variable holding a credential, never the value.
"""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="NEXORA_", extra="ignore")

    # --- Core -------------------------------------------------------------
    # Defaults to a local SQLite file so the app runs with zero external
    # services for development/tests. Docker/production point this at Postgres.
    database_url: str = "sqlite:///./nexora.db"
    log_level: str = "INFO"
    environment: str = "development"

    # Comma-separated exact origins allowed to make credentialed (cookie)
    # requests. Empty = same-origin only (the docker-compose setup serves the
    # SPA and proxies /api from one nginx origin, so no CORS is needed).
    cors_allowed_origins: str = ""

    # --- Auth / sessions --------------------------------------------------
    session_ttl_hours: int = 24 * 14
    session_cookie_name: str = "nexora_session"
    # Set to false only for local HTTP development; must be true wherever the
    # app is reachable over the network (cookies HttpOnly/Secure/SameSite).
    session_cookie_secure: bool = True
    auth_rate_limit_attempts: int = 10
    auth_rate_limit_window_seconds: int = 300
    # Comma-separated emails granted the admin role at registration. The very
    # first account registered is always an admin (self-hosted convention).
    admin_emails: str = ""

    # --- API ----------------------------------------------------------------
    default_page_size: int = 20
    max_page_size: int = 100
    # Generic per-client request budget for the search/quote endpoints, which
    # fan out to external providers: protects our own provider quotas from a
    # single misbehaving browser tab.
    api_rate_limit_per_minute: int = 120

    # --- Portfolio ----------------------------------------------------------
    # A manually entered / CSV-imported price is flagged stale past this age.
    price_freshness_hours: int = 24
    csv_import_max_bytes: int = 2_000_000
    csv_import_max_rows: int = 5_000

    # --- Market data (app/market) -------------------------------------------
    # Which adapter serves each asset family; "null" disables live data for
    # that family (manual prices only). See specs/DATA_SOURCES.md.
    market_equity_provider: str = "yahoo"  # yahoo | finnhub | null
    market_crypto_provider: str = "coingecko"  # coingecko | null
    market_fx_provider: str = "frankfurter"  # frankfurter | null
    # A live quote is refreshed at most this often (specs/README.md: "cible
    # indicative : 15 minutes"); the worker refreshes held/watched instruments
    # on the same cadence. Between refreshes, the cached quote is served with
    # its age shown — never a fresh call per page view.
    quote_freshness_minutes: int = 15
    market_refresh_interval_seconds: int = 15 * 60
    market_history_max_days: int = 365 * 10
    # Hard per-process request budgets per provider (token bucket). Kept well
    # under each provider's published limit; see specs/DATA_SOURCES.md.
    yahoo_rate_limit_per_minute: int = 20
    coingecko_rate_limit_per_minute: int = 8
    finnhub_rate_limit_per_minute: int = 30
    frankfurter_rate_limit_per_minute: int = 20
    market_http_timeout_seconds: float = 10.0
    market_auto_disable_after_failures: int = 10
    market_circuit_reset_seconds: int = 600
    finnhub_api_key_env_var: str = "FINNHUB_API_KEY"
    coingecko_api_key_env_var: str = "COINGECKO_API_KEY"
    # Sent on every outbound market request; some providers require a
    # descriptive UA. No personal data.
    market_user_agent: str = "NeXora-personal-dashboard/1.0"
    # Used only when a provider setting is "fixture" (tests, demo profile).
    market_fixture_path: str = "tests/fixtures/market_data/demo_quotes.json"

    # --- News & events (app/news) -------------------------------------------
    # Automatic per-instrument company news through Finnhub (needs the key
    # named by finnhub_api_key_env_var; silently off without it).
    news_auto_company_news: bool = True
    news_freshness_minutes: int = 60
    event_freshness_minutes: int = 24 * 60
    ingestion_interval_seconds: int = 15 * 60
    ingestion_jitter_seconds: int = 60
    http_timeout_seconds: float = 10.0
    max_retries: int = 3
    retry_backoff_base_seconds: float = 1.0
    circuit_breaker_failure_threshold: int = 5
    circuit_breaker_reset_seconds: int = 300
    # Past this many *consecutive* failures a provider disables itself rather
    # than re-probing forever unsupervised (see specs/DATA_SOURCES.md incident).
    auto_disable_after_failures: int = 15
    dedup_title_similarity_threshold: float = 0.88
    dedup_time_window_hours: int = 72
    worker_metrics_port: int = 9100

    # --- Prediction (app/prediction) — experimental, off by default ---------
    # Kill switch (specs/PREDICTION.md: "désactivée par défaut", "kill switch").
    prediction_enabled: bool = False
    prediction_max_observations: int = 4000
    prediction_min_observations: int = 120
    prediction_max_experiments_per_user: int = 50


settings = Settings()
