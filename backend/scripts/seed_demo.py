"""Seed a small, entirely synthetic demo dataset: one asset and one provider
of each type (RSS, JSON API, ICS calendar), each pointed at the fixture
files already committed under tests/fixtures/ and served locally by the
`demo-fixtures` static file server in docker-compose.yml.

No real provider, account, or API key is used or required - this exists so
a fresh checkout can see the pipeline (fetch -> normalize -> dedupe ->
score -> summarize -> serve) working end to end without any external
network access. Safe to re-run: it upserts by name/symbol.
"""

from __future__ import annotations

import math
import os
import random
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import func, select

from app.db import SessionLocal
from app.models import Instrument, OhlcBar, Provider, ProviderFeed

DEMO_HISTORY_DAYS = 730

DEMO_FIXTURES_BASE_URL = os.environ.get("DEMO_FIXTURES_BASE_URL", "http://localhost:8090")


def _get_or_create_asset(db) -> Instrument:
    asset = db.scalar(select(Instrument).where(Instrument.symbol == "DEMO"))
    if asset is None:
        # Bound to the offline "fixture" market provider so the demo profile
        # also shows quotes/candles without any network call
        # (NEXORA_MARKET_EQUITY_PROVIDER=fixture in the demo compose profile).
        asset = Instrument(
            symbol="DEMO",
            name="Demo SA",
            exchange="XPAR",
            currency="EUR",
            asset_class="action",
            provider="fixture",
            provider_symbol="DEMO",
        )
        db.add(asset)
        db.flush()
    return asset


def _ensure_demo_history(db, instrument: Instrument) -> int:
    """Two years of deterministic synthetic daily bars (seeded random walk)
    so charts, indicators, the quant toolbox and the prediction lab all have
    something to chew on offline. Clearly labelled `source="fixture"`."""
    existing = db.scalar(select(func.count(OhlcBar.id)).where(OhlcBar.instrument_id == instrument.id)) or 0
    if existing >= DEMO_HISTORY_DAYS:
        return 0
    rng = random.Random(42)  # noqa: S311 - synthetic demo data, not security
    today = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    known = {b.as_of for b in db.scalars(select(OhlcBar).where(OhlcBar.instrument_id == instrument.id))}
    price = 30.0
    written = 0
    for i in range(DEMO_HISTORY_DAYS, 0, -1):
        day = today - timedelta(days=i)
        if day.weekday() >= 5:
            continue  # no bars on weekends, like a real exchange
        ret = rng.gauss(0.0003, 0.014)
        open_ = price
        price = max(1.0, price * math.exp(ret))
        high = max(open_, price) * (1 + abs(rng.gauss(0, 0.004)))
        low = min(open_, price) * (1 - abs(rng.gauss(0, 0.004)))
        if day in known:
            continue
        db.add(
            OhlcBar(
                instrument_id=instrument.id,
                interval="1d",
                as_of=day,
                open=Decimal(f"{open_:.4f}"),
                high=Decimal(f"{high:.4f}"),
                low=Decimal(f"{low:.4f}"),
                close=Decimal(f"{price:.4f}"),
                volume=Decimal(int(rng.uniform(8000, 30000))),
                currency=instrument.currency,
                source="fixture",
            )
        )
        written += 1
    return written


def _get_or_create_provider(db, name: str, type_: str, config: dict, license_note: str) -> Provider:
    provider = db.scalar(select(Provider).where(Provider.name == name))
    if provider is None:
        provider = Provider(name=name, type=type_, config=config, license_note=license_note)
        db.add(provider)
        db.flush()
    else:
        provider.config = config
        provider.license_note = license_note
    return provider


def _ensure_feed(db, provider: Provider, url: str, instrument_id: str) -> None:
    existing = next((f for f in provider.feeds if f.url == url), None)
    if existing is None:
        db.add(ProviderFeed(provider_id=provider.id, url=url, extra_config={"instrument_id": instrument_id}))


def seed() -> None:
    db = SessionLocal()
    try:
        asset = _get_or_create_asset(db)

        rss_provider = _get_or_create_provider(
            db,
            "demo-issuer-rss",
            "rss",
            config={"base_confidence": 0.7},
            license_note="Fixture RSS feed for local demo only - not a real issuer feed.",
        )
        _ensure_feed(db, rss_provider, f"{DEMO_FIXTURES_BASE_URL}/rss/valid_feed.xml", asset.id)

        media_provider = _get_or_create_provider(
            db,
            "demo-media-rss",
            "rss",
            config={"base_confidence": 0.6},
            license_note="Fixture RSS feed for local demo only - not a real media outlet.",
        )
        _ensure_feed(db, media_provider, f"{DEMO_FIXTURES_BASE_URL}/rss/corroborating_feed.xml", asset.id)

        calendar_provider = _get_or_create_provider(
            db,
            "demo-issuer-calendar",
            "calendar_ics",
            config={"base_confidence": 0.85},
            license_note="Fixture ICS calendar for local demo only - not a real issuer calendar.",
        )
        _ensure_feed(db, calendar_provider, f"{DEMO_FIXTURES_BASE_URL}/calendar/upcoming_events.ics", asset.id)

        bars = _ensure_demo_history(db, asset)
        db.commit()
        print(f"seeded demo asset '{asset.symbol}' ({asset.id}), {bars} synthetic daily bars and 3 demo providers")
    finally:
        db.close()


if __name__ == "__main__":
    seed()
