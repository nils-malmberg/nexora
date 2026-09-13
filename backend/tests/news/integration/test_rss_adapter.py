from datetime import UTC

import httpx
import pytest
import respx

from app.news.adapters.base import AdapterParseError
from app.news.adapters.rss_atom import RssAtomAdapter
from tests.conftest import read_fixture_bytes

FEED_URL = "https://example-issuer.test/rss.xml"


def _adapter() -> RssAtomAdapter:
    return RssAtomAdapter(provider_id="prov-rss", provider_config={})


@respx.mock
def test_fetch_parses_valid_feed():
    respx.get(FEED_URL).mock(return_value=httpx.Response(200, content=read_fixture_bytes("rss", "valid_feed.xml")))
    result = _adapter().fetch(FEED_URL, {"instrument_id": "asset-1"}, since=None)
    assert len(result.items) == 2
    assert result.items[0].title == "Résultats du troisième trimestre publiés"
    assert result.items[0].asset_hint == "asset-1"


@respx.mock
def test_fetch_raises_on_malformed_feed():
    respx.get(FEED_URL).mock(return_value=httpx.Response(200, content=read_fixture_bytes("rss", "malformed.xml")))
    with pytest.raises(AdapterParseError):
        _adapter().fetch(FEED_URL, {}, since=None)


@respx.mock
def test_normalize_skips_item_without_publication_date():
    respx.get(FEED_URL).mock(return_value=httpx.Response(200, content=read_fixture_bytes("rss", "no_date.xml")))
    result = _adapter().fetch(FEED_URL, {}, since=None)
    adapter = _adapter()
    normalized = []
    skipped = 0
    for record in result.items:
        try:
            normalized.append(adapter.normalize(record))
        except AdapterParseError:
            skipped += 1
    assert skipped == 1
    assert len(normalized) == 1
    assert normalized[0].title == "Communique avec date"


@respx.mock
def test_normalize_produces_canonical_url_and_content_hash():
    respx.get(FEED_URL).mock(return_value=httpx.Response(200, content=read_fixture_bytes("rss", "valid_feed.xml")))
    adapter = _adapter()
    result = adapter.fetch(FEED_URL, {}, since=None)
    normalized = adapter.normalize(result.items[0])
    assert "utm_source" not in normalized.url
    assert normalized.content_hash
    assert normalized.category == "resultats"
    assert normalized.kind == "fact"


@respx.mock
def test_fetch_since_filters_older_items():
    from datetime import datetime

    respx.get(FEED_URL).mock(return_value=httpx.Response(200, content=read_fixture_bytes("rss", "valid_feed.xml")))
    since = datetime(2026, 9, 2, tzinfo=UTC)
    result = _adapter().fetch(FEED_URL, {}, since=since)
    assert len(result.items) == 1
    assert result.items[0].title.startswith("Nomination")


@respx.mock
def test_health_reports_ok():
    respx.get(FEED_URL).mock(return_value=httpx.Response(200, content=read_fixture_bytes("rss", "valid_feed.xml")))
    status = _adapter().health(FEED_URL, {})
    assert status.ok is True


@respx.mock
def test_health_reports_failure_on_http_error():
    respx.get(FEED_URL).mock(return_value=httpx.Response(503))
    status = _adapter().health(FEED_URL, {})
    assert status.ok is False


@respx.mock
def test_fetch_raises_rate_limited_on_429():
    from app.news.adapters.base import AdapterRateLimited

    respx.get(FEED_URL).mock(return_value=httpx.Response(429, headers={"Retry-After": "30"}))
    with pytest.raises(AdapterRateLimited) as exc_info:
        _adapter().fetch(FEED_URL, {}, since=None)
    assert exc_info.value.retry_after_seconds == 30.0


@respx.mock
def test_fetch_raises_timeout():
    from app.news.adapters.base import AdapterTimeout

    respx.get(FEED_URL).mock(side_effect=httpx.TimeoutException("timed out"))
    with pytest.raises(AdapterTimeout):
        _adapter().fetch(FEED_URL, {}, since=None)
