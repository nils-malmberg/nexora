"""Automatic company news (Finnhub) per catalog instrument: created lazily,
refreshed on demand at most once per freshness window, worker limited to
tracked instruments, explicit statuses when nothing can be fetched."""

from __future__ import annotations

import httpx
import respx
from sqlalchemy import select

from app.models import Provider, ProviderFeed
from app.news import auto as news_auto
from tests.conftest import auth_headers

COMPANY_NEWS = [
    {
        "id": 101,
        "headline": "Demo SA raises guidance",
        "url": "https://news.example/1",
        "summary": "Sales up.",
        "datetime": 1768507200,
        "related": "DEMO",
        "source": "Wire",
    },
    {
        "id": 102,
        "headline": "Demo SA appoints new CFO",
        "url": "https://news.example/2",
        "summary": "",
        "datetime": 1768420800,
        "related": "DEMO",
        "source": "Wire",
    },
]


def _demo(client, csrf):
    resp = client.post(
        "/api/v1/market/catalog",
        json={
            "provider": "fixture",
            "provider_symbol": "DEMO",
            "symbol": "DEMO",
            "name": "Demo SA",
            "asset_class": "action",
        },
        headers=auth_headers(csrf),
    )
    return resp.json()["instrument"]


def test_refresh_without_key_explains_instead_of_empty(registered_user, monkeypatch):
    client, csrf, _ = registered_user
    monkeypatch.delenv("FINNHUB_API_KEY", raising=False)
    instrument = _demo(client, csrf)
    body = client.post(f"/api/v1/instruments/{instrument['id']}/news/refresh", headers=auth_headers(csrf)).json()
    assert body["status"] == "not_configured" and body["configured"] is False
    assert "FINNHUB_API_KEY" in body["detail"]
    status = client.get("/api/v1/providers/status").json()
    assert status["auto_news"]["configured"] is False and status["auto_news"]["env_var"] == "FINNHUB_API_KEY"


@respx.mock
def test_refresh_creates_feed_fetches_once_and_serves_news(registered_user, monkeypatch, db_session):
    client, csrf, _ = registered_user
    monkeypatch.setenv("FINNHUB_API_KEY", "test-key-never-logged")
    news_auto.reset_marks()
    route = respx.get("https://finnhub.io/api/v1/company-news").mock(
        return_value=httpx.Response(200, json=COMPANY_NEWS)
    )
    instrument = _demo(client, csrf)

    body = client.post(f"/api/v1/instruments/{instrument['id']}/news/refresh", headers=auth_headers(csrf)).json()
    assert body["status"] == "refreshed" and body["run_status"] == "success" and body["items_total"] == 2
    assert route.call_count == 1
    request = route.calls[0].request
    assert request.url.params["symbol"] == "DEMO" and request.url.params["token"] == "test-key-never-logged"
    assert "from" in request.url.params and "to" in request.url.params

    provider = db_session.scalar(select(Provider).where(Provider.name == news_auto.AUTO_PROVIDER_NAME))
    feed = db_session.scalar(select(ProviderFeed).where(ProviderFeed.provider_id == provider.id))
    assert feed.instrument_id == instrument["id"] and feed.extra_config["query_params"]["symbol"] == "DEMO"

    listed = client.get(f"/api/v1/instruments/{instrument['id']}/news").json()["items"]
    assert {i["title"] for i in listed} == {"Demo SA raises guidance", "Demo SA appoints new CFO"}
    assert listed[0]["provider_name"] == news_auto.AUTO_PROVIDER_NAME and listed[0]["instrument_ids"] == [
        instrument["id"]
    ]

    # Second refresh inside the freshness window: served from what's stored, no request.
    again = client.post(f"/api/v1/instruments/{instrument['id']}/news/refresh", headers=auth_headers(csrf)).json()
    assert again["status"] == "cached" and route.call_count == 1

    # A private instrument is not eligible (no provider symbol, no company news).
    private = client.post(
        "/api/v1/instruments",
        json={"symbol": "MYFUND", "name": "Fonds privé", "asset_class": "actif_prive", "currency": "EUR"},
        headers=auth_headers(csrf),
    ).json()
    assert (
        client.post(f"/api/v1/instruments/{private['id']}/news/refresh", headers=auth_headers(csrf)).json()["status"]
        == "not_eligible"
    )


@respx.mock
def test_failed_fetch_is_reported_and_never_retried_in_a_loop(registered_user, monkeypatch):
    client, csrf, _ = registered_user
    monkeypatch.setenv("FINNHUB_API_KEY", "bad-key")
    news_auto.reset_marks()
    route = respx.get("https://finnhub.io/api/v1/company-news").mock(
        return_value=httpx.Response(401, json={"error": "Invalid API key"})
    )
    instrument = _demo(client, csrf)
    body = client.post(f"/api/v1/instruments/{instrument['id']}/news/refresh", headers=auth_headers(csrf)).json()
    assert body["status"] == "failed" and body["error_code"] == "all_feeds_failed"
    assert "clé invalide" in body["detail"]
    # Retries are bounded by the pipeline's policy; the next click is answered from the mark, not Finnhub.
    calls_after_first = route.call_count
    again = client.post(f"/api/v1/instruments/{instrument['id']}/news/refresh", headers=auth_headers(csrf)).json()
    assert again["status"] == "cached" and route.call_count == calls_after_first


def test_worker_only_refreshes_tracked_instruments(registered_user, monkeypatch, db_session):
    client, csrf, _ = registered_user
    monkeypatch.setenv("FINNHUB_API_KEY", "k")
    demo = _demo(client, csrf)
    other = client.post(
        "/api/v1/market/catalog",
        json={
            "provider": "fixture",
            "provider_symbol": "USDEMO",
            "symbol": "USDEMO",
            "name": "US Demo",
            "asset_class": "action",
        },
        headers=auth_headers(csrf),
    ).json()["instrument"]
    from app.models import Instrument

    news_auto.ensure_feed(db_session, db_session.get(Instrument, demo["id"]))
    news_auto.ensure_feed(db_session, db_session.get(Instrument, other["id"]))
    db_session.commit()
    provider = db_session.scalar(select(Provider).where(Provider.name == news_auto.AUTO_PROVIDER_NAME))
    assert news_auto.feeds_to_refresh(db_session, provider) == []  # nothing held or watched yet
    client.post("/api/v1/market/watchlist", json={"instrument_id": demo["id"]}, headers=auth_headers(csrf))
    feeds = news_auto.feeds_to_refresh(db_session, provider)
    assert [f.instrument_id for f in feeds] == [demo["id"]]
    # The worker creates the missing feed of a newly watched instrument itself.
    client.post("/api/v1/market/watchlist", json={"instrument_id": other["id"]}, headers=auth_headers(csrf))
    db_session.execute(ProviderFeed.__table__.delete().where(ProviderFeed.instrument_id == other["id"]))
    db_session.commit()
    assert news_auto.ensure_feeds_for_tracked(db_session) == 1
    assert {f.instrument_id for f in news_auto.feeds_to_refresh(db_session, provider)} == {demo["id"], other["id"]}
    # Hand-configured providers are untouched by the filter.
    manual = Provider(name="issuer-rss", type="rss")
    db_session.add(manual)
    db_session.commit()
    assert news_auto.feeds_to_refresh(db_session, manual) is None
