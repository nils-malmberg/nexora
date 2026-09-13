from datetime import UTC, datetime

from app.models import NewsItem, NewsItemAsset
from app.news.pipeline.dedupe import find_exact_news_duplicate, find_near_duplicate_news


def _make_news_item(db_session, provider_id, instrument_id, title, content_hash, publication_at):
    item = NewsItem(
        provider_id=provider_id,
        kind="fact",
        category="resultats",
        title=title,
        excerpt="extrait",
        publication_at=publication_at,
        timezone="UTC",
        url=f"https://example.test/{content_hash}",
        provenance="test",
        confidence=0.7,
        content_hash=content_hash,
    )
    db_session.add(item)
    db_session.flush()
    if instrument_id:
        db_session.add(
            NewsItemAsset(
                news_item_id=item.id, instrument_id=instrument_id, match_confidence=1.0, match_method="explicit"
            )
        )
    db_session.commit()
    return item


def test_find_exact_duplicate_by_content_hash(db_session, make_provider, make_instrument):
    provider = make_provider("prov-a", "rss")
    asset = make_instrument()
    when = datetime(2026, 9, 1, tzinfo=UTC)
    item = _make_news_item(db_session, provider.id, asset.id, "Titre", "hash-1", when)

    found = find_exact_news_duplicate(db_session, "hash-1")
    assert found is not None
    assert found.id == item.id
    assert find_exact_news_duplicate(db_session, "hash-2") is None


def test_near_duplicate_same_provider_is_duplicate_of(db_session, make_provider, make_instrument):
    provider = make_provider("prov-a", "rss")
    asset = make_instrument()
    when = datetime(2026, 9, 1, tzinfo=UTC)
    _make_news_item(db_session, provider.id, asset.id, "Resultats du troisieme trimestre en hausse", "hash-1", when)

    match = find_near_duplicate_news(
        db_session,
        instrument_id=asset.id,
        provider_id=provider.id,
        title="Resultats du troisieme trimestre en hausse",
        publication_at=when,
        exclude_content_hash="hash-2",
    )
    assert match is not None
    assert match.relation_type == "duplicate_of"


def test_near_duplicate_different_provider_corroborates(db_session, make_provider, make_instrument):
    provider_a = make_provider("prov-a", "rss")
    provider_b = make_provider("prov-b", "rss")
    asset = make_instrument()
    when = datetime(2026, 9, 1, tzinfo=UTC)
    _make_news_item(
        db_session, provider_a.id, asset.id, "Resultats du troisieme trimestre en hausse de 8%", "hash-1", when
    )

    match = find_near_duplicate_news(
        db_session,
        instrument_id=asset.id,
        provider_id=provider_b.id,
        title="Resultats du troisieme trimestre en nette hausse de 8%",
        publication_at=when,
        exclude_content_hash="hash-2",
    )
    assert match is not None
    assert match.relation_type == "corroborates"


def test_dissimilar_titles_are_not_matched(db_session, make_provider, make_instrument):
    provider = make_provider("prov-a", "rss")
    asset = make_instrument()
    when = datetime(2026, 9, 1, tzinfo=UTC)
    _make_news_item(db_session, provider.id, asset.id, "Nomination d'un administrateur independant", "hash-1", when)

    match = find_near_duplicate_news(
        db_session,
        instrument_id=asset.id,
        provider_id=provider.id,
        title="Resultats du troisieme trimestre en forte hausse",
        publication_at=when,
        exclude_content_hash="hash-2",
    )
    assert match is None


def test_outside_time_window_is_not_matched(db_session, make_provider, make_instrument):
    from datetime import timedelta

    provider = make_provider("prov-a", "rss")
    asset = make_instrument()
    when = datetime(2026, 9, 1, tzinfo=UTC)
    _make_news_item(db_session, provider.id, asset.id, "Resultats du troisieme trimestre en hausse", "hash-1", when)

    match = find_near_duplicate_news(
        db_session,
        instrument_id=asset.id,
        provider_id=provider.id,
        title="Resultats du troisieme trimestre en hausse",
        publication_at=when + timedelta(hours=200),
        exclude_content_hash="hash-2",
    )
    assert match is None
