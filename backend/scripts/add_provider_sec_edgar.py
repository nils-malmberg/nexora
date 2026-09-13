"""Register the real SEC EDGAR company-filings feed for one tracked asset.

Read specs/DATA_SOURCES.md ("SEC EDGAR") before running this: it documents
the license, the mandatory User-Agent header, and the 10 req/s rate limit.

This performs REAL, idempotent database writes (get-or-create by symbol /
provider name / feed URL - safe to re-run) but no network call itself; the
first real HTTP request to sec.gov happens only when the provider is synced
(see the `sync` commands printed at the end of this script, or
`python -m app.worker.cli sync sec-edgar-filings`).

Required environment variable:
  SEC_EDGAR_USER_AGENT - e.g. "NeXora-personal-dashboard contact@example.com"
                         SEC blocks requests without a descriptive contact.
"""

from __future__ import annotations

import os
import sys

from sqlalchemy import select

from app.db import SessionLocal
from app.models import Instrument, Provider, ProviderFeed

CIK = "0000320193"  # Apple Inc.
SYMBOL = "AAPL"
NAME = "Apple Inc."
MARKET = "NASDAQ"
CURRENCY = "USD"

SEC_USER_AGENT = os.environ.get("SEC_EDGAR_USER_AGENT")


def get_or_create_asset(db) -> Instrument:
    asset = db.scalar(select(Instrument).where(Instrument.symbol == SYMBOL))
    if asset is None:
        asset = Instrument(symbol=SYMBOL, name=NAME, exchange=MARKET, currency=CURRENCY, asset_class="action")
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


def ensure_feed(db, provider: Provider, url: str, instrument_id: str, extra_config: dict) -> None:
    existing = next((f for f in provider.feeds if f.url == url), None)
    if existing is None:
        db.add(
            ProviderFeed(
                provider_id=provider.id, url=url, extra_config={"instrument_id": instrument_id, **extra_config}
            )
        )
    else:
        existing.extra_config = {"instrument_id": instrument_id, **extra_config}


def main() -> None:
    if not SEC_USER_AGENT:
        print(
            "SEC_EDGAR_USER_AGENT is not set. SEC blocks requests without a descriptive "
            "contact (e.g. 'NeXora-personal-dashboard you@example.com'). Add it to .env "
            "and export it before running this script.",
            file=sys.stderr,
        )
        sys.exit(1)

    db = SessionLocal()
    try:
        asset = get_or_create_asset(db)
        provider = get_or_create_provider(
            db,
            "sec-edgar-filings",
            "rss",
            config={"user_agent": SEC_USER_AGENT, "base_confidence": 0.9},
            license_note=(
                "SEC EDGAR - information publique du gouvernement federal americain "
                "(sec.gov/privacy). 10 req/s max, User-Agent obligatoire, aucune cle requise."
            ),
        )
        feed_url = (
            "https://www.sec.gov/cgi-bin/browse-edgar"
            f"?action=getcompany&CIK={CIK}&type=&dateb=&owner=include&count=40&output=atom"
        )
        ensure_feed(db, provider, feed_url, asset.id, extra_config={"category_hint": "reglementation"})
        db.commit()

        print(f"asset='{asset.symbol}' ({asset.id})")
        print(f"provider='{provider.name}' ({provider.id}), feed -> {feed_url}")
        print("\nSynchroniser :")
        print(f"  python -m app.worker.cli sync {provider.name}")
        print("\nVerifier :")
        print("  curl -s http://localhost:8000/api/v1/providers/status | python3 -m json.tool")
        print(f"  curl -s http://localhost:8000/api/v1/instruments/{asset.id}/news | python3 -m json.tool")
    finally:
        db.close()


if __name__ == "__main__":
    main()
