from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import models
from app.api.deps import get_db
from app.api.main import app
from app.config import settings
from app.db import Base


@pytest.fixture()
def client():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, future=True)
    session = session_factory()

    def override_get_db():
        try:
            yield session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    try:
        yield TestClient(app), session
    finally:
        app.dependency_overrides.clear()
        session.close()
        engine.dispose()


def _seed_news_item(session, asset, provider, **overrides):
    now = datetime.now(UTC)
    defaults = dict(
        provider_id=provider.id,
        kind="fact",
        category="resultats",
        title="Titre",
        excerpt="Extrait",
        publication_at=now,
        timezone="UTC",
        url="https://example.test/a",
        provenance="test",
        confidence=0.8,
        content_hash="hash-" + overrides.get("title", "x"),
    )
    defaults.update(overrides)
    item = models.NewsItem(**defaults)
    session.add(item)
    session.flush()
    session.add(
        models.NewsItemAsset(news_item_id=item.id, asset_id=asset.id, match_confidence=1.0, match_method="explicit")
    )
    session.commit()
    return item


def test_health_and_ready(client):
    http, _ = client
    assert http.get("/health").json() == {"status": "ok"}
    assert http.get("/ready").json() == {"status": "ready"}


def test_list_and_get_asset(client):
    http, session = client
    asset = models.Asset(symbol="DEMO", name="Demo SA", market="XPAR", currency="EUR")
    session.add(asset)
    session.commit()

    listed = http.get("/api/v1/assets").json()
    assert len(listed) == 1
    assert listed[0]["symbol"] == "DEMO"

    got = http.get(f"/api/v1/assets/{asset.id}")
    assert got.status_code == 200
    assert got.json()["name"] == "Demo SA"

    assert http.get("/api/v1/assets/does-not-exist").status_code == 404


def test_asset_news_returns_items_with_provenance_and_freshness(client):
    http, session = client
    asset = models.Asset(symbol="DEMO", name="Demo SA")
    provider = models.Provider(name="issuer-rss", type="rss")
    session.add_all([asset, provider])
    session.commit()
    _seed_news_item(session, asset, provider, title="Item 1")

    resp = http.get(f"/api/v1/assets/{asset.id}/news")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["items"]) == 1
    item = body["items"][0]
    assert item["provider_name"] == "issuer-rss"
    assert item["provenance"] == "test"
    assert "stale" in item
    assert item["asset_ids"] == [asset.id]
    assert resp.headers["etag"]


def test_asset_news_pagination_cursor(client):
    http, session = client
    asset = models.Asset(symbol="DEMO", name="Demo SA")
    provider = models.Provider(name="issuer-rss", type="rss")
    session.add_all([asset, provider])
    session.commit()
    base = datetime.now(UTC)
    for i in range(3):
        _seed_news_item(
            session,
            asset,
            provider,
            title=f"Item {i}",
            content_hash=f"hash-{i}",
            publication_at=base - timedelta(hours=i),
        )

    first_page = http.get(f"/api/v1/assets/{asset.id}/news", params={"limit": 2}).json()
    assert len(first_page["items"]) == 2
    assert first_page["next_cursor"] is not None

    second_page = http.get(
        f"/api/v1/assets/{asset.id}/news", params={"limit": 2, "cursor": first_page["next_cursor"]}
    ).json()
    assert len(second_page["items"]) == 1
    assert second_page["next_cursor"] is None

    seen_titles = {i["title"] for i in first_page["items"]} | {i["title"] for i in second_page["items"]}
    assert seen_titles == {"Item 0", "Item 1", "Item 2"}


def test_asset_news_text_search(client):
    http, session = client
    asset = models.Asset(symbol="DEMO", name="Demo SA")
    provider = models.Provider(name="issuer-rss", type="rss")
    session.add_all([asset, provider])
    session.commit()
    _seed_news_item(session, asset, provider, title="Dividende exceptionnel annonce", content_hash="hash-a")
    _seed_news_item(
        session, asset, provider, title="Autre sujet", excerpt="mention du dividende ici", content_hash="hash-b"
    )
    _seed_news_item(session, asset, provider, title="Sans rapport", content_hash="hash-c")

    resp = http.get(f"/api/v1/assets/{asset.id}/news", params={"q": "dividende"})
    assert resp.status_code == 200
    titles = {i["title"] for i in resp.json()["items"]}
    assert titles == {"Dividende exceptionnel annonce", "Autre sujet"}


def test_asset_news_text_search_no_match_returns_empty(client):
    http, session = client
    asset = models.Asset(symbol="DEMO", name="Demo SA")
    provider = models.Provider(name="issuer-rss", type="rss")
    session.add_all([asset, provider])
    session.commit()
    _seed_news_item(session, asset, provider, title="Titre")
    resp = http.get(f"/api/v1/assets/{asset.id}/news", params={"q": "zzz-no-match-zzz"})
    assert resp.status_code == 200
    assert resp.json()["items"] == []


def test_asset_news_unknown_category_is_rejected(client):
    http, session = client
    asset = models.Asset(symbol="DEMO", name="Demo SA")
    session.add(asset)
    session.commit()
    resp = http.get(f"/api/v1/assets/{asset.id}/news", params={"category": "not-a-real-category"})
    assert resp.status_code == 400
    body = resp.json()
    assert body["code"] == "http_400"
    assert "request_id" in body


def test_asset_news_404_for_unknown_asset(client):
    http, _ = client
    resp = http.get("/api/v1/assets/unknown-asset/news")
    assert resp.status_code == 404


def test_timeline_merges_news_and_events(client):
    http, session = client
    asset = models.Asset(symbol="DEMO", name="Demo SA")
    provider = models.Provider(name="issuer-rss", type="rss")
    session.add_all([asset, provider])
    session.commit()
    _seed_news_item(session, asset, provider, title="News item")

    event = models.Event(
        asset_id=asset.id,
        provider_id=provider.id,
        type="assemblee_generale",
        starts_at=datetime.now(UTC) + timedelta(days=10),
        status="confirme",
        last_verified_at=datetime.now(UTC),
        content_hash="event-hash-1",
    )
    session.add(event)
    session.commit()

    resp = http.get(f"/api/v1/assets/{asset.id}/timeline")
    assert resp.status_code == 200
    entries = resp.json()
    assert {e["entry_type"] for e in entries} == {"news", "event"}


def test_upcoming_events_excludes_cancelled_by_default(client):
    http, session = client
    asset = models.Asset(symbol="DEMO", name="Demo SA")
    provider = models.Provider(name="issuer-cal", type="calendar_ics")
    session.add_all([asset, provider])
    session.commit()
    session.add_all(
        [
            models.Event(
                asset_id=asset.id,
                provider_id=provider.id,
                type="dividende",
                starts_at=datetime.now(UTC) + timedelta(days=5),
                status="confirme",
                last_verified_at=datetime.now(UTC),
                content_hash="e1",
            ),
            models.Event(
                asset_id=asset.id,
                provider_id=provider.id,
                type="conference",
                starts_at=datetime.now(UTC) + timedelta(days=6),
                status="annule",
                last_verified_at=datetime.now(UTC),
                content_hash="e2",
            ),
        ]
    )
    session.commit()

    resp = http.get("/api/v1/events/upcoming")
    assert resp.status_code == 200
    types = [e["type"] for e in resp.json()]
    assert types == ["dividende"]


def test_timeline_rejects_unknown_granularity(client):
    http, session = client
    asset = models.Asset(symbol="DEMO", name="Demo SA")
    session.add(asset)
    session.commit()
    resp = http.get(f"/api/v1/assets/{asset.id}/timeline", params={"granularity": "fortnight"})
    assert resp.status_code == 400


def test_timeline_date_only_event_uses_period_basis(client):
    http, session = client
    asset = models.Asset(symbol="DEMO", name="Demo SA")
    provider = models.Provider(name="issuer-cal", type="calendar_ics")
    session.add_all([asset, provider])
    session.commit()
    session.add(
        models.Event(
            asset_id=asset.id,
            provider_id=provider.id,
            type="maturite",
            starts_at=None,
            period_label="2026-12-01",
            status="unknown",
            last_verified_at=datetime.now(UTC),
            content_hash="e-maturity",
        )
    )
    session.commit()

    resp = http.get(f"/api/v1/assets/{asset.id}/timeline")
    assert resp.status_code == 200
    entry = next(e for e in resp.json() if e["entry_type"] == "event")
    assert entry["date_basis"] == "period"
    assert entry["bucket"] == "2026-12"


def test_timeline_category_filter_applies_to_news_only(client):
    http, session = client
    asset = models.Asset(symbol="DEMO", name="Demo SA")
    provider = models.Provider(name="issuer-rss", type="rss")
    session.add_all([asset, provider])
    session.commit()
    _seed_news_item(session, asset, provider, title="Resultats", category="resultats")
    _seed_news_item(session, asset, provider, title="Gouvernance", category="gouvernance", content_hash="hash-gov")

    resp = http.get(f"/api/v1/assets/{asset.id}/timeline", params={"category": "resultats"})
    assert resp.status_code == 200
    titles = [e["news_item"]["title"] for e in resp.json() if e["entry_type"] == "news"]
    assert titles == ["Resultats"]


def test_news_item_shows_corroboration_link(client):
    http, session = client
    asset = models.Asset(symbol="DEMO", name="Demo SA")
    provider_a = models.Provider(name="issuer-rss", type="rss")
    provider_b = models.Provider(name="media-rss", type="rss")
    session.add_all([asset, provider_a, provider_b])
    session.commit()
    item_a = _seed_news_item(session, asset, provider_a, title="Original", content_hash="hash-a")
    item_b = _seed_news_item(session, asset, provider_b, title="Confirmation independante", content_hash="hash-b")
    session.add(
        models.NewsItemRelation(news_item_id=item_b.id, related_news_item_id=item_a.id, relation_type="corroborates")
    )
    session.commit()

    resp = http.get(f"/api/v1/assets/{asset.id}/news")
    body = {i["title"]: i for i in resp.json()["items"]}
    assert len(body["Confirmation independante"]["corroborated_by"]) == 1
    assert body["Confirmation independante"]["corroborated_by"][0]["news_item_id"] == item_a.id


def test_upcoming_events_display_timezone_converts_starts_at(client):
    http, session = client
    asset = models.Asset(symbol="DEMO", name="Demo SA")
    provider = models.Provider(name="issuer-cal", type="calendar_ics")
    session.add_all([asset, provider])
    session.commit()
    session.add(
        models.Event(
            asset_id=asset.id,
            provider_id=provider.id,
            type="assemblee_generale",
            starts_at=datetime(2026, 10, 15, 12, 0, tzinfo=UTC),
            status="confirme",
            last_verified_at=datetime.now(UTC),
            content_hash="e-agm",
        )
    )
    session.commit()

    resp = http.get("/api/v1/events/upcoming", params={"tz": "Europe/Paris"})
    assert resp.status_code == 200
    event = resp.json()[0]
    assert event["starts_at"].startswith("2026-10-15T14:00:00")
    assert event["timezone"] == "Europe/Paris"


def test_upcoming_events_rejects_unknown_timezone(client):
    http, _ = client
    resp = http.get("/api/v1/events/upcoming", params={"tz": "Not/AZone"})
    assert resp.status_code == 400


def test_providers_status(client):
    http, session = client
    provider = models.Provider(name="issuer-rss", type="rss", circuit_state="open", consecutive_failures=5)
    session.add(provider)
    session.commit()

    resp = http.get("/api/v1/providers/status")
    assert resp.status_code == 200
    body = resp.json()
    assert body[0]["healthy"] is False
    assert body[0]["consecutive_failures"] == 5


def test_admin_sync_requires_key(client, monkeypatch):
    http, session = client
    provider = models.Provider(name="issuer-rss", type="rss")
    session.add(provider)
    session.commit()

    monkeypatch.setattr(settings, "admin_api_key", "")
    resp = http.post(f"/api/v1/admin/providers/{provider.id}/sync")
    assert resp.status_code == 503

    monkeypatch.setattr(settings, "admin_api_key", "s3cr3t-admin-key")
    resp = http.post(f"/api/v1/admin/providers/{provider.id}/sync")
    assert resp.status_code == 401

    resp = http.post(
        f"/api/v1/admin/providers/{provider.id}/sync",
        headers={"X-Admin-Key": "s3cr3t-admin-key"},
    )
    assert resp.status_code == 200
    assert resp.json()["provider_id"] == provider.id


def test_cors_allows_cross_origin_requests(client):
    http, _ = client
    resp = http.get("/api/v1/assets", headers={"Origin": "http://localhost:5173"})
    assert resp.status_code == 200
    assert resp.headers["access-control-allow-origin"] == "*"


def test_metrics_endpoint_exposes_prometheus_format(client):
    http, _ = client
    resp = http.get("/metrics")
    assert resp.status_code == 200
    assert "nexora_" in resp.text or resp.text == ""
