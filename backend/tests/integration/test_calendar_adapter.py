import httpx
import pytest
import respx

from app.adapters.calendar_ics import CalendarIcsAdapter
from tests.conftest import read_fixture_bytes

CAL_URL = "https://example-issuer.test/ir/calendar.ics"


def _adapter() -> CalendarIcsAdapter:
    return CalendarIcsAdapter(provider_id="prov-cal", provider_config={})


@respx.mock
def test_fetch_parses_all_vevents():
    respx.get(CAL_URL).mock(
        return_value=httpx.Response(200, content=read_fixture_bytes("calendar", "upcoming_events.ics"))
    )
    result = _adapter().fetch(CAL_URL, {"asset_id": "asset-1"}, since=None)
    assert len(result.items) == 4


@respx.mock
def test_normalize_maps_status_and_timezone_correctly():
    respx.get(CAL_URL).mock(
        return_value=httpx.Response(200, content=read_fixture_bytes("calendar", "upcoming_events.ics"))
    )
    adapter = _adapter()
    result = adapter.fetch(CAL_URL, {"asset_id": "asset-1"}, since=None)
    normalized = {n.type: n for n in (adapter.normalize(r) for r in result.items)}

    agm = normalized["assemblee_generale"]
    assert agm.status == "confirme"
    assert agm.starts_at is not None
    assert agm.starts_at.utcoffset().total_seconds() == 0  # stored in UTC
    # 14:00 CEST (UTC+2) in October -> 12:00 UTC
    assert agm.starts_at.hour == 12

    dividend = normalized["dividende"]
    assert dividend.status == "previsionnel"
    assert dividend.amount == 1.25
    assert dividend.currency == "EUR"

    cancelled = normalized["autre"]
    assert cancelled.status == "annule"


@respx.mock
def test_all_day_event_keeps_period_label_without_inventing_a_time():
    respx.get(CAL_URL).mock(
        return_value=httpx.Response(200, content=read_fixture_bytes("calendar", "upcoming_events.ics"))
    )
    adapter = _adapter()
    result = adapter.fetch(CAL_URL, {"asset_id": "asset-1"}, since=None)
    normalized = [adapter.normalize(r) for r in result.items]
    maturity = next(n for n in normalized if n.type == "maturite")
    assert maturity.starts_at is None
    assert maturity.period_label == "2026-12-01"


@respx.mock
def test_asset_hint_falls_back_to_custom_property_when_feed_not_bound():
    respx.get(CAL_URL).mock(
        return_value=httpx.Response(200, content=read_fixture_bytes("calendar", "upcoming_events.ics"))
    )
    adapter = _adapter()
    result = adapter.fetch(CAL_URL, {}, since=None)  # no feed-level asset_id
    normalized = adapter.normalize(result.items[0])
    assert normalized.asset_hint == "DEMO"


@respx.mock
def test_fetch_raises_parse_error_on_malformed_ics():
    respx.get(CAL_URL).mock(return_value=httpx.Response(200, content=b"not an ics file at all"))
    from app.adapters.base import AdapterParseError

    with pytest.raises(AdapterParseError):
        _adapter().fetch(CAL_URL, {}, since=None)


@respx.mock
def test_fetch_raises_rate_limited_on_429():
    from app.adapters.base import AdapterRateLimited

    respx.get(CAL_URL).mock(return_value=httpx.Response(429, headers={"Retry-After": "15"}))
    with pytest.raises(AdapterRateLimited) as exc_info:
        _adapter().fetch(CAL_URL, {}, since=None)
    assert exc_info.value.retry_after_seconds == 15.0


@respx.mock
def test_health_reports_ok_and_failure():
    respx.get(CAL_URL).mock(
        return_value=httpx.Response(200, content=read_fixture_bytes("calendar", "upcoming_events.ics"))
    )
    assert _adapter().health(CAL_URL, {}).ok is True

    respx.get(CAL_URL).mock(return_value=httpx.Response(503))
    assert _adapter().health(CAL_URL, {}).ok is False
