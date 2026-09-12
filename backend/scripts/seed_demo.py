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

import os

from sqlalchemy import select

from app.db import SessionLocal
from app.models import Asset, Provider, ProviderFeed

DEMO_FIXTURES_BASE_URL = os.environ.get("DEMO_FIXTURES_BASE_URL", "http://localhost:8090")


def _get_or_create_asset(db) -> Asset:
    asset = db.scalar(select(Asset).where(Asset.symbol == "DEMO"))
    if asset is None:
        asset = Asset(symbol="DEMO", name="Demo SA", market="XPAR", currency="EUR")
        db.add(asset)
        db.flush()
    return asset


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


def _ensure_feed(db, provider: Provider, url: str, asset_id: str) -> None:
    existing = next((f for f in provider.feeds if f.url == url), None)
    if existing is None:
        db.add(ProviderFeed(provider_id=provider.id, url=url, extra_config={"asset_id": asset_id}))


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

        db.commit()
        print(f"seeded demo asset '{asset.symbol}' ({asset.id}) and 3 demo providers")
    finally:
        db.close()


if __name__ == "__main__":
    seed()
