"""Register the real Finnhub company-news feed for one tracked asset.

Read specs/DATA_SOURCES.md ("Finnhub") before running this: free tier,
personal/non-commercial use, ~60 calls/minute, requires your own API key.

Idempotent (get-or-create by symbol / provider name / feed URL - safe to
re-run). No network call happens here; the first real request to Finnhub
happens only when this provider is synced (see the commands printed at the
end, or `python -m app.worker.cli sync finnhub-news`).

Required environment variable:
  FINNHUB_API_KEY - from your account at https://finnhub.io (free tier)
"""

from __future__ import annotations

import os
import sys

from sqlalchemy import select

from app.db import SessionLocal
from app.models import Asset, Provider, ProviderFeed

SYMBOL = "AAPL"
NAME = "Apple Inc."
MARKET = "NASDAQ"
CURRENCY = "USD"

FINNHUB_MAPPING = {
    "external_id": "id",
    "title": "headline",
    "url": "url",
    "summary": "summary",
    "published_at": "datetime",
    "asset_symbol": "related",
}


def get_or_create_asset(db) -> Asset:
    asset = db.scalar(select(Asset).where(Asset.symbol == SYMBOL))
    if asset is None:
        asset = Asset(symbol=SYMBOL, name=NAME, market=MARKET, currency=CURRENCY)
        db.add(asset)
        db.flush()
    return asset


def get_or_create_provider(db, name: str, type_: str, config: dict, license_note: str) -> Provider:
    provider = db.scalar(select(Provider).where(Provider.name == name))
    if provider is None:
        provider = Provider(name=name, type=type_, config=config, license_note=license_note)
        db.add(provider)
        db.flush()
    else:
        provider.config = config
        provider.license_note = license_note
    return provider


def ensure_feed(db, provider: Provider, url: str, asset_id: str, extra_config: dict) -> None:
    existing = next((f for f in provider.feeds if f.url == url), None)
    if existing is None:
        db.add(ProviderFeed(provider_id=provider.id, url=url, extra_config={"asset_id": asset_id, **extra_config}))
    else:
        existing.extra_config = {"asset_id": asset_id, **extra_config}


def main() -> None:
    if not os.environ.get("FINNHUB_API_KEY"):
        print(
            "FINNHUB_API_KEY is not set. Sign up for a free key at finnhub.io and add it "
            "to .env before running this script.",
            file=sys.stderr,
        )
        sys.exit(1)

    db = SessionLocal()
    try:
        asset = get_or_create_asset(db)
        provider = get_or_create_provider(
            db,
            "finnhub-news",
            "json_api",
            config={
                "content_type": "news",
                "base_confidence": 0.6,
                "timestamp_format": "unix_seconds",
                "mapping": FINNHUB_MAPPING,
                "pagination": {"style": "none"},
                # Finnhub's own OpenAPI spec declares `token` as a query
                # parameter, not a header (securityDefinitions: {"name":
                # "token", "in": "query"}) - verified against
                # https://finnhub.io/static/swagger.json.
                "auth": {"in": "query", "param": "token", "env_var": "FINNHUB_API_KEY"},
            },
            license_note=(
                "Finnhub free tier - usage personnel/non commercial. "
                "~60 appels/minute. CGU a reverifier par l'utilisateur sur finnhub.io."
            ),
        )
        # {{today}}/{{today-Nd}} are resolved at fetch time (see
        # app/adapters/common.py:resolve_query_param_templates), so this
        # rolling 30-day window stays current on every sync rather than
        # freezing to the date this script was run.
        ensure_feed(
            db,
            provider,
            "https://finnhub.io/api/v1/company-news",
            asset.id,
            extra_config={"query_params": {"symbol": SYMBOL, "from": "{{today-30d}}", "to": "{{today}}"}},
        )
        db.commit()

        print(f"asset='{asset.symbol}' ({asset.id})")
        print(f"provider='{provider.name}' ({provider.id})")
        print("\nSynchroniser :")
        print(f"  python -m app.worker.cli sync {provider.name}")
        print("\nVerifier :")
        print("  curl -s http://localhost:8000/api/v1/providers/status | python3 -m json.tool")
        print(f"  curl -s http://localhost:8000/api/v1/assets/{asset.id}/news | python3 -m json.tool")
    finally:
        db.close()


if __name__ == "__main__":
    main()
