"""News, timeline and events API - now served by the unified app: every
endpoint requires a signed-in user and only exposes instruments visible to
that user (shared catalog or their own)."""

from datetime import UTC, datetime, timedelta

import pytest

from app import models
from tests.conftest import auth_headers, register


@pytest.fixture()
def news_client(client, db_session):
    """(authenticated http client, db session, csrf token) - the registered
    user is the first account, hence an admin."""
    csrf, _ = register(client)
    return client, db_session, csrf


def _instrument(session, **overrides) -> models.Instrument:
    fields = dict(symbol="DEMO", name="Demo SA", exchange="XPAR", currency="EUR", asset_class="action")
    fields.update(overrides)
    instrument = models.Instrument(**fields)
    session.add(instrument)
    session.commit()
    return instrument


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
        models.NewsItemAsset(
            news_item_id=item.id, instrument_id=asset.id, match_confidence=1.0, match_method="explicit"
        )
    )
    session.commit()
    return item


def test_health_and_ready(news_client):
    http, _, _ = news_client
    assert http.get("/health").json() == {"status": "ok"}
    assert http.get("/ready").json() == {"status": "ready"}


def test_shared_catalog_instrument_is_visible_but_not_listed_until_tracked(news_client):
    http, session, csrf = news_client
    asset = _instrument(session)

    # The working set only lists what the user owns, holds or watches...
    assert http.get("/api/v1/instruments").json() == []
    # ...but a shared catalog entry is readable by anyone signed in.
    got = http.get(f"/api/v1/instruments/{asset.id}")
    assert got.status_code == 200
    assert got.json()["name"] == "Demo SA"
    assert got.json()["is_shared"] is True
    assert http.get("/api/v1/instruments/does-not-exist").status_code == 404

    # Watching it puts it in the working set.
    resp = http.post("/api/v1/market/watchlist", json={"instrument_id": asset.id}, headers=auth_headers(csrf))
    assert resp.status_code == 201, resp.text
    assert [i["symbol"] for i in http.get("/api/v1/instruments").json()] == ["DEMO"]


def test_news_endpoints_require_authentication(client, db_session):
    asset = _instrument(db_session)
    assert client.get(f"/api/v1/instruments/{asset.id}/news").status_code == 401
    assert client.get(f"/api/v1/instruments/{asset.id}/timeline").status_code == 401
    assert client.get("/api/v1/events/upcoming").status_code == 401


def test_another_users_private_instrument_news_is_404(news_client):
    http, session, _ = news_client
    other_csrf, other_id = register(http, email="bob@example.com")  # switches the cookie to bob
    private = _instrument(session, user_id=other_id, symbol="PRIV")
    # back to alice
    http.post("/api/v1/auth/login", json={"email": "alice@example.com", "password": "correct horse battery staple"})
    assert http.get(f"/api/v1/instruments/{private.id}/news").status_code == 404
    assert http.get(f"/api/v1/instruments/{private.id}/timeline").status_code == 404


def test_asset_news_returns_items_with_provenance_and_freshness(news_client):
    http, session, _ = news_client
    asset = _instrument(session)
    provider = models.Provider(name="issuer-rss", type="rss")
    session.add(provider)
    session.commit()
    _seed_news_item(session, asset, provider, title="Item 1")

    resp = http.get(f"/api/v1/instruments/{asset.id}/news")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["items"]) == 1
    item = body["items"][0]
    assert item["provider_name"] == "issuer-rss"
    assert item["provenance"] == "test"
    assert "stale" in item
    assert item["instrument_ids"] == [asset.id]
    assert resp.headers["etag"]


def test_asset_news_pagination_cursor(news_client):
    http, session, _ = news_client
    asset = _instrument(session)
    provider = models.Provider(name="issuer-rss", type="rss")
    session.add(provider)
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

    first_page = http.get(f"/api/v1/instruments/{asset.id}/news", params={"limit": 2}).json()
    assert len(first_page["items"]) == 2
    assert first_page["next_cursor"] is not None

    second_page = http.get(
        f"/api/v1/instruments/{asset.id}/news", params={"limit": 2, "cursor": first_page["next_cursor"]}
    ).json()
    assert len(second_page["items"]) == 1
    assert second_page["next_cursor"] is None

    seen_titles = {i["title"] for i in first_page["items"]} | {i["title"] for i in second_page["items"]}
    assert seen_titles == {"Item 0", "Item 1", "Item 2"}


def test_asset_news_text_search(news_client):
    http, session, _ = news_client
    asset = _instrument(session)
    provider = models.Provider(name="issuer-rss", type="rss")
    session.add(provider)
    session.commit()
    _seed_news_item(session, asset, provider, title="Dividende exceptionnel annonce", content_hash="hash-a")
    _seed_news_item(
        session, asset, provider, title="Autre sujet", excerpt="mention du dividende ici", content_hash="hash-b"
    )
    _seed_news_item(session, asset, provider, title="Sans rapport", content_hash="hash-c")

    resp = http.get(f"/api/v1/instruments/{asset.id}/news", params={"q": "dividende"})
    assert resp.status_code == 200
    titles = {i["title"] for i in resp.json()["items"]}
    assert titles == {"Dividende exceptionnel annonce", "Autre sujet"}


def test_asset_news_text_search_no_match_returns_empty(news_client):
    http, session, _ = news_client
    asset = _instrument(session)
    provider = models.Provider(name="issuer-rss", type="rss")
    session.add(provider)
    session.commit()
    _seed_news_item(session, asset, provider, title="Titre")
    resp = http.get(f"/api/v1/instruments/{asset.id}/news", params={"q": "zzz-no-match-zzz"})
    assert resp.status_code == 200
    assert resp.json()["items"] == []


def test_asset_news_unknown_category_is_rejected(news_client):
    http, session, _ = news_client
    asset = _instrument(session)
    resp = http.get(f"/api/v1/instruments/{asset.id}/news", params={"category": "not-a-real-category"})
    assert resp.status_code == 400
    body = resp.json()
    assert body["code"] == "http_400"
    assert "request_id" in body


def test_asset_news_404_for_unknown_asset(news_client):
    http, _, _ = news_client
    resp = http.get("/api/v1/instruments/unknown-asset/news")
    assert resp.status_code == 404


def test_timeline_merges_news_and_events(news_client):
    http, session, _ = news_client
    asset = _instrument(session)
    provider = models.Provider(name="issuer-rss", type="rss")
    session.add(provider)
    session.commit()
    _seed_news_item(session, asset, provider, title="News item")

    event = models.Event(
        instrument_id=asset.id,
        provider_id=provider.id,
        type="assemblee_generale",
        starts_at=datetime.now(UTC) + timedelta(days=10),
        status="confirme",
        last_verified_at=datetime.now(UTC),
        content_hash="event-hash-1",
    )
    session.add(event)
    session.commit()

    resp = http.get(f"/api/v1/instruments/{asset.id}/timeline")
    assert resp.status_code == 200
    entries = resp.json()
    assert {e["entry_type"] for e in entries} == {"news", "event"}


def test_upcoming_events_excludes_cancelled_by_default(news_client):
    http, session, _ = news_client
    asset = _instrument(session)
    provider = models.Provider(name="issuer-cal", type="calendar_ics")
    session.add(provider)
    session.commit()
    session.add_all(
        [
            models.Event(
                instrument_id=asset.id,
                provider_id=provider.id,
                type="dividende",
                starts_at=datetime.now(UTC) + timedelta(days=5),
                status="confirme",
                last_verified_at=datetime.now(UTC),
                content_hash="e1",
            ),
            models.Event(
                instrument_id=asset.id,
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


def test_timeline_rejects_unknown_granularity(news_client):
    http, session, _ = news_client
    asset = _instrument(session)
    resp = http.get(f"/api/v1/instruments/{asset.id}/timeline", params={"granularity": "fortnight"})
    assert resp.status_code == 400


def test_timeline_date_only_event_uses_period_basis(news_client):
    http, session, _ = news_client
    asset = _instrument(session)
    provider = models.Provider(name="issuer-cal", type="calendar_ics")
    session.add(provider)
    session.commit()
    session.add(
        models.Event(
            instrument_id=asset.id,
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

    resp = http.get(f"/api/v1/instruments/{asset.id}/timeline")
    assert resp.status_code == 200
    entry = next(e for e in resp.json() if e["entry_type"] == "event")
    assert entry["date_basis"] == "period"
    assert entry["bucket"] == "2026-12"


def test_timeline_category_filter_applies_to_news_only(news_client):
    http, session, _ = news_client
    asset = _instrument(session)
    provider = models.Provider(name="issuer-rss", type="rss")
    session.add(provider)
    session.commit()
    _seed_news_item(session, asset, provider, title="Resultats", category="resultats")
    _seed_news_item(session, asset, provider, title="Gouvernance", category="gouvernance", content_hash="hash-gov")

    resp = http.get(f"/api/v1/instruments/{asset.id}/timeline", params={"category": "resultats"})
    assert resp.status_code == 200
    titles = [e["news_item"]["title"] for e in resp.json() if e["entry_type"] == "news"]
    assert titles == ["Resultats"]


def test_news_item_shows_corroboration_link(news_client):
    http, session, _ = news_client
    asset = _instrument(session)
    provider_a = models.Provider(name="issuer-rss", type="rss")
    provider_b = models.Provider(name="media-rss", type="rss")
    session.add_all([provider_a, provider_b])
    session.commit()
    item_a = _seed_news_item(session, asset, provider_a, title="Original", content_hash="hash-a")
    item_b = _seed_news_item(session, asset, provider_b, title="Confirmation independante", content_hash="hash-b")
    session.add(
        models.NewsItemRelation(news_item_id=item_b.id, related_news_item_id=item_a.id, relation_type="corroborates")
    )
    session.commit()

    resp = http.get(f"/api/v1/instruments/{asset.id}/news")
    body = {i["title"]: i for i in resp.json()["items"]}
    assert len(body["Confirmation independante"]["corroborated_by"]) == 1
    assert body["Confirmation independante"]["corroborated_by"][0]["news_item_id"] == item_a.id


def test_upcoming_events_display_timezone_converts_starts_at(news_client):
    http, session, _ = news_client
    asset = _instrument(session)
    provider = models.Provider(name="issuer-cal", type="calendar_ics")
    session.add(provider)
    session.commit()
    session.add(
        models.Event(
            instrument_id=asset.id,
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


def test_upcoming_events_rejects_unknown_timezone(news_client):
    http, _, _ = news_client
    resp = http.get("/api/v1/events/upcoming", params={"tz": "Not/AZone"})
    assert resp.status_code == 400


def test_providers_status(news_client):
    http, session, _ = news_client
    provider = models.Provider(name="issuer-rss", type="rss", circuit_state="open", consecutive_failures=5)
    session.add(provider)
    session.commit()

    resp = http.get("/api/v1/providers/status")
    assert resp.status_code == 200
    body = resp.json()
    assert body["news"][0]["healthy"] is False
    assert body["news"][0]["consecutive_failures"] == 5
    assert {m["role"] for m in body["market"]} == {"equity", "crypto", "fx"}
    assert "prediction_enabled" in body


def test_admin_sync_requires_admin_role_and_csrf(news_client):
    http, session, csrf = news_client
    provider = models.Provider(name="issuer-rss", type="rss")
    session.add(provider)
    session.commit()

    # Missing CSRF token: refused even for the admin.
    resp = http.post(f"/api/v1/admin/news-providers/{provider.id}/sync")
    assert resp.status_code == 403

    resp = http.post(f"/api/v1/admin/news-providers/{provider.id}/sync", headers=auth_headers(csrf))
    assert resp.status_code == 200, resp.text
    assert resp.json()["provider_id"] == provider.id

    # A second, non-admin user is refused.
    bob_csrf, _ = register(http, email="bob@example.com")
    resp = http.post(f"/api/v1/admin/news-providers/{provider.id}/sync", headers=auth_headers(bob_csrf))
    assert resp.status_code == 403
    assert http.get("/api/v1/admin/news-providers").status_code == 403


def test_same_origin_default_sends_no_cors_header_but_security_headers(news_client):
    http, _, _ = news_client
    resp = http.get("/api/v1/instruments", headers={"Origin": "http://evil.example"})
    assert resp.status_code == 200
    assert "access-control-allow-origin" not in resp.headers
    assert resp.headers["x-content-type-options"] == "nosniff"
    assert resp.headers["x-frame-options"] == "DENY"
    assert "content-security-policy" in resp.headers


def test_metrics_endpoint_exposes_prometheus_format(news_client):
    http, _, _ = news_client
    resp = http.get("/metrics")
    assert resp.status_code == 200
    assert "nexora_" in resp.text or resp.text == ""
