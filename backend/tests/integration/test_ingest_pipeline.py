import httpx
import respx

from app.models import Event, EventStatusHistory, IngestionRun, NewsItem, NewsItemRelation, ProviderFeed
from app.pipeline.ingest import run_provider
from tests.conftest import read_fixture_bytes

RSS_URL = "https://example-issuer.test/rss.xml"
MEDIA_RSS_URL = "https://example-media.test/rss.xml"
CAL_URL = "https://example-issuer.test/ir/calendar.ics"


def _add_feed(db_session, provider, url, asset_id=None):
    feed = ProviderFeed(provider_id=provider.id, url=url, extra_config={"asset_id": asset_id} if asset_id else {})
    db_session.add(feed)
    db_session.commit()
    db_session.refresh(provider)
    return feed


@respx.mock
def test_run_provider_inserts_news_items(db_session, make_provider, make_asset):
    asset = make_asset(symbol="DEMO")
    provider = make_provider("issuer-rss", "rss")
    _add_feed(db_session, provider, RSS_URL, asset_id=asset.id)
    respx.get(RSS_URL).mock(return_value=httpx.Response(200, content=read_fixture_bytes("rss", "valid_feed.xml")))

    run = run_provider(db_session, provider)

    assert run.status == "success"
    assert run.counts["inserted"] == 2
    items = db_session.query(NewsItem).all()
    assert len(items) == 2
    assert all(item.summary is not None or item.excerpt for item in items)
    assert all(item.relevance_score > 0 for item in items)


@respx.mock
def test_run_provider_is_idempotent_on_repeated_fetch(db_session, make_provider, make_asset):
    asset = make_asset(symbol="DEMO")
    provider = make_provider("issuer-rss", "rss")
    _add_feed(db_session, provider, RSS_URL, asset_id=asset.id)
    respx.get(RSS_URL).mock(return_value=httpx.Response(200, content=read_fixture_bytes("rss", "valid_feed.xml")))

    run_provider(db_session, provider)

    # Simulate a full re-crawl (e.g. a provider that ignores incremental
    # filtering and always returns its whole recent window): without this,
    # our own adapter-side `since` filter would legitimately exclude these
    # already-old fixture dates on the second run, which would prove nothing
    # about dedup/idempotency.
    db_session.refresh(provider)
    provider.last_success_at = None
    db_session.commit()

    second_run = run_provider(db_session, provider)

    assert second_run.counts.get("inserted", 0) == 0
    assert second_run.counts.get("updated", 0) == 2
    assert db_session.query(NewsItem).count() == 2


@respx.mock
def test_corroboration_relation_created_across_providers(db_session, make_provider, make_asset):
    asset = make_asset(symbol="DEMO")
    provider_a = make_provider("issuer-rss", "rss")
    provider_b = make_provider("media-rss", "rss")
    _add_feed(db_session, provider_a, RSS_URL, asset_id=asset.id)
    _add_feed(db_session, provider_b, MEDIA_RSS_URL, asset_id=asset.id)
    respx.get(RSS_URL).mock(return_value=httpx.Response(200, content=read_fixture_bytes("rss", "valid_feed.xml")))
    respx.get(MEDIA_RSS_URL).mock(
        return_value=httpx.Response(200, content=read_fixture_bytes("rss", "corroborating_feed.xml"))
    )

    run_provider(db_session, provider_a)
    run_provider(db_session, provider_b)

    relations = db_session.query(NewsItemRelation).all()
    assert len(relations) == 1
    assert relations[0].relation_type == "corroborates"


@respx.mock
def test_partial_failure_isolated_per_record(db_session, make_provider, make_asset):
    make_asset(symbol="DEMO")
    provider = make_provider("issuer-rss", "rss")
    _add_feed(db_session, provider, RSS_URL)
    respx.get(RSS_URL).mock(return_value=httpx.Response(200, content=read_fixture_bytes("rss", "no_date.xml")))

    run = run_provider(db_session, provider)

    assert run.status == "partial"
    assert run.counts["skipped_parse_errors"] == 1
    assert db_session.query(NewsItem).count() == 1


@respx.mock
def test_all_feeds_failing_opens_circuit_after_threshold(db_session, make_provider, monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "retry_backoff_base_seconds", 0.0)
    provider = make_provider("issuer-rss", "rss")
    _add_feed(db_session, provider, RSS_URL)
    respx.get(RSS_URL).mock(return_value=httpx.Response(503))

    for _ in range(settings.circuit_breaker_failure_threshold):
        run = run_provider(db_session, provider)
        assert run.status == "failed"

    db_session.refresh(provider)
    assert provider.circuit_state == "open"

    # A further attempt is skipped outright (circuit open) rather than making a network call.
    respx.get(RSS_URL).mock(side_effect=AssertionError("should not be called while circuit is open"))
    run = run_provider(db_session, provider)
    assert run.error_code == "circuit_open"


@respx.mock
def test_calendar_status_change_is_traceable(db_session, make_provider, make_asset):
    asset = make_asset(symbol="DEMO")
    provider = make_provider("issuer-calendar", "calendar_ics")
    _add_feed(db_session, provider, CAL_URL, asset_id=asset.id)

    respx.get(CAL_URL).mock(
        return_value=httpx.Response(200, content=read_fixture_bytes("calendar", "upcoming_events.ics"))
    )
    run_provider(db_session, provider)

    agm = db_session.query(Event).filter(Event.type == "assemblee_generale").one()
    assert agm.status == "confirme"
    assert len(agm.status_history) == 1

    respx.get(CAL_URL).mock(
        return_value=httpx.Response(200, content=read_fixture_bytes("calendar", "corrected_event.ics"))
    )
    run_provider(db_session, provider)

    db_session.refresh(agm)
    assert agm.status == "annule"
    history = (
        db_session.query(EventStatusHistory)
        .filter(EventStatusHistory.event_id == agm.id)
        .order_by(EventStatusHistory.changed_at)
        .all()
    )
    assert [h.new_status for h in history] == ["confirme", "annule"]
    assert len(agm.sources) == 2  # both the original and corrected source URLs are kept


@respx.mock
def test_disabled_provider_is_skipped(db_session, make_provider):
    provider = make_provider("issuer-rss", "rss", enabled=False)
    _add_feed(db_session, provider, RSS_URL)
    run = run_provider(db_session, provider)
    assert run.error_code == "provider_disabled"
    assert db_session.query(IngestionRun).count() == 1
