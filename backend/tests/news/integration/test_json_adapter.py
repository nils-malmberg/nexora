import json
from datetime import UTC, datetime

import httpx
import pytest
import respx

from app.news.adapters.base import AdapterMisconfigured, AdapterParseError, AdapterRateLimited
from app.news.adapters.json_api import JsonApiAdapter
from tests.conftest import FIXTURES_DIR

API_URL = "https://example-news-api.test/v1/articles"

MAPPING = {
    "external_id": "id",
    "title": "headline",
    "url": "link",
    "summary": "excerpt",
    "published_at": "published_at",
    "category": "category",
    "language": "lang",
    "asset_symbol": "ticker",
}
PAGINATION = {
    "style": "page",
    "param": "page",
    "start": 1,
    "items_path": "data.items",
    "has_more_path": "data.has_more",
}


def _page(name: str) -> dict:
    return json.loads((FIXTURES_DIR / "json_api" / name).read_text())


def _adapter(extra_config: dict | None = None) -> JsonApiAdapter:
    return JsonApiAdapter(
        provider_id="prov-json",
        provider_config={"mapping": MAPPING, "pagination": PAGINATION, **(extra_config or {})},
    )


@respx.mock
def test_fetch_follows_pagination_until_has_more_false():
    route = respx.get(API_URL)
    route.side_effect = [
        httpx.Response(200, json=_page("page1.json")),
        httpx.Response(200, json=_page("page2.json")),
    ]
    result = _adapter().fetch(API_URL, {}, since=None)
    assert len(result.items) == 2
    assert route.call_count == 2


@respx.mock
def test_fetch_raises_rate_limited():
    respx.get(API_URL).mock(return_value=httpx.Response(429, headers={"Retry-After": "5"}))
    with pytest.raises(AdapterRateLimited):
        _adapter().fetch(API_URL, {}, since=None)


@respx.mock
def test_fetch_raises_parse_error_on_invalid_json():
    respx.get(API_URL).mock(return_value=httpx.Response(200, content=b"not json"))
    with pytest.raises(AdapterParseError):
        _adapter().fetch(API_URL, {}, since=None)


@respx.mock
def test_normalize_skips_record_missing_title_but_keeps_others():
    respx.get(API_URL).mock(return_value=httpx.Response(200, json=_page("incomplete.json")))
    adapter = _adapter()
    result = adapter.fetch(API_URL, {}, since=None)
    normalized = []
    skipped = 0
    for record in result.items:
        try:
            normalized.append(adapter.normalize(record))
        except AdapterParseError:
            skipped += 1
    assert skipped == 1
    assert len(normalized) == 1
    assert "malgre" in normalized[0].title.lower()


def test_missing_mapping_is_misconfigured():
    adapter = JsonApiAdapter(provider_id="prov-json", provider_config={})
    with pytest.raises(AdapterMisconfigured):
        adapter.fetch(API_URL, {}, since=None)


@respx.mock
def test_auth_header_resolved_from_env_var(monkeypatch):
    monkeypatch.setenv("DEMO_NEWS_API_KEY", "s3cr3t")
    route = respx.get(API_URL).mock(return_value=httpx.Response(200, json=_page("page2.json")))
    adapter = _adapter({"auth": {"header": "Authorization", "env_var": "DEMO_NEWS_API_KEY", "prefix": "Bearer "}})
    adapter.fetch(API_URL, {}, since=None)
    sent_request = route.calls.last.request
    assert sent_request.headers["Authorization"] == "Bearer s3cr3t"


def test_missing_auth_env_var_raises_misconfigured_rather_than_silently_unauthenticated():
    adapter = _adapter({"auth": {"header": "Authorization", "env_var": "NOT_SET_ENV_VAR"}})
    with pytest.raises(AdapterMisconfigured):
        adapter.fetch(API_URL, {}, since=None)


@respx.mock
def test_auth_query_param_resolved_from_env_var(monkeypatch):
    """Some APIs (e.g. Finnhub, per its own OpenAPI spec) authenticate via a
    query parameter rather than a header."""
    monkeypatch.setenv("DEMO_NEWS_API_KEY", "s3cr3t")
    route = respx.get(API_URL).mock(return_value=httpx.Response(200, json=_page("page2.json")))
    adapter = _adapter({"auth": {"in": "query", "param": "token", "env_var": "DEMO_NEWS_API_KEY"}})
    adapter.fetch(API_URL, {}, since=None)
    sent_request = route.calls.last.request
    assert dict(sent_request.url.params)["token"] == "s3cr3t"


@respx.mock
def test_health_reports_ok_and_failure():
    respx.get(API_URL).mock(return_value=httpx.Response(200, json=_page("page2.json")))
    assert _adapter().health(API_URL, {}).ok is True

    respx.get(API_URL).mock(return_value=httpx.Response(503))
    assert _adapter().health(API_URL, {}).ok is False


@respx.mock
def test_fetch_raises_timeout():
    from app.news.adapters.base import AdapterTimeout

    respx.get(API_URL).mock(side_effect=httpx.TimeoutException("timed out"))
    with pytest.raises(AdapterTimeout):
        _adapter().fetch(API_URL, {}, since=None)


@respx.mock
def test_unix_timestamp_format_parses_finnhub_shaped_response():
    """Finnhub's CompanyNews.datetime is a Unix timestamp per its own OpenAPI
    spec, not ISO 8601. Before `timestamp_format` this crashed with an
    uncaught AttributeError (int has no .strip()) instead of a graceful
    AdapterParseError or a correctly parsed date."""
    finnhub_mapping = {
        "external_id": "id",
        "title": "headline",
        "url": "url",
        "summary": "summary",
        "published_at": "datetime",
        "asset_symbol": "related",
    }
    adapter = JsonApiAdapter(
        provider_id="prov-finnhub",
        provider_config={
            "mapping": finnhub_mapping,
            "pagination": {"style": "none"},
            "timestamp_format": "unix_seconds",
        },
    )
    respx.get(API_URL).mock(return_value=httpx.Response(200, json=_page("finnhub_company_news.json")))
    result = adapter.fetch(API_URL, {}, since=None)
    assert len(result.items) == 1
    normalized = adapter.normalize(result.items[0])
    assert normalized.publication_at.year == 2026
    assert normalized.publication_at.month == 9
    assert normalized.publication_at.day == 1


@respx.mock
def test_rolling_date_query_params_are_resolved_at_fetch_time():
    """A feed's query_params can use {{today}}/{{today-Nd}} so a fixed
    ProviderFeed config (e.g. Finnhub's required from/to range) stays
    current on every scheduled sync instead of being frozen to whatever
    date the feed was created on."""
    route = respx.get(API_URL).mock(return_value=httpx.Response(200, json=_page("page2.json")))
    adapter = _adapter()
    adapter.fetch(API_URL, {"query_params": {"symbol": "AAPL", "to": "{{today}}", "from": "{{today-30d}}"}}, since=None)
    sent_params = dict(route.calls.last.request.url.params)
    assert sent_params["symbol"] == "AAPL"
    assert sent_params["to"] == datetime.now(UTC).strftime("%Y-%m-%d")


@respx.mock
def test_event_content_type_requires_event_date_or_period():
    adapter = JsonApiAdapter(
        provider_id="prov-json-events",
        provider_config={
            "content_type": "event",
            "mapping": {**MAPPING, "event_at": "event_date"},
            "pagination": PAGINATION,
        },
    )
    respx.get(API_URL).mock(return_value=httpx.Response(200, json=_page("page2.json")))  # no event_date field
    result = adapter.fetch(API_URL, {}, since=None)
    with pytest.raises(AdapterParseError):
        adapter.normalize(result.items[0])
