"""Application configuration.

All values are read from environment variables (or a local `.env` file that
is never committed). No secret, key, or credential is ever hardcoded here —
see specs/SECURITY.md.
"""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="NEXORA_PORTFOLIO_", extra="ignore")

    # Defaults to a local SQLite file so the module runs with zero external
    # services for development/tests. Production points this at the
    # `nexora_portfolio` Postgres database (see docker-compose.yml) — a
    # separate database from the News & Events module, not a shared schema.
    database_url: str = "sqlite:///./nexora_portfolio.db"

    session_ttl_hours: int = 24 * 14
    session_cookie_name: str = "nexora_portfolio_session"
    # Set to false only for local HTTP development; must be true wherever the
    # app is reachable over the network, per specs/SECURITY.md (cookies
    # HttpOnly/Secure/SameSite).
    session_cookie_secure: bool = True

    # In-memory sliding-window rate limit on auth endpoints (login/register).
    # Single-instance limitation, documented in README - same trade-off the
    # News & Events module made by not running a dedicated cache/Redis.
    auth_rate_limit_attempts: int = 10
    auth_rate_limit_window_seconds: int = 300

    # A position/price is "stale" (still shown, but flagged) past this age.
    # Manual/CSV-imported prices are not live ticks, so this is measured in
    # days by default, not minutes.
    price_freshness_hours: int = 24

    default_page_size: int = 20
    max_page_size: int = 100

    # CSV import (specs/PORTFOLIO_IMPORTS.md: "limitation de taille/type").
    # The raw file itself is never persisted (see app/domain/csv_import.py) —
    # these bounds exist to keep in-memory parsing and the stored, structured
    # row data cheap, not to protect a stored file.
    csv_import_max_bytes: int = 2_000_000
    csv_import_max_rows: int = 5_000

    log_level: str = "INFO"
    environment: str = "development"

    cors_allowed_origins: str = "http://localhost:5174"


settings = Settings()
