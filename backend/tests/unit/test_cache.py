from datetime import UTC, datetime, timedelta

from app.pipeline.cache import age_seconds, is_stale, snapshot_freshness_label


def test_snapshot_freshness_label_estimated_takes_priority():
    assert snapshot_freshness_label(is_estimated=True, has_known_date=True) == "estimated"
    assert snapshot_freshness_label(is_estimated=True, has_known_date=False) == "estimated"


def test_snapshot_freshness_label_unknown_when_no_date():
    assert snapshot_freshness_label(is_estimated=False, has_known_date=False) == "unknown"


def test_snapshot_freshness_label_delayed_by_default():
    assert snapshot_freshness_label(is_estimated=False, has_known_date=True) == "delayed"


def test_is_stale_true_past_ttl():
    now = datetime(2026, 9, 10, 12, 0, tzinfo=UTC)
    reference = now - timedelta(minutes=90)
    assert is_stale(reference, ttl_minutes=60, now=now) is True


def test_is_stale_false_within_ttl():
    now = datetime(2026, 9, 10, 12, 0, tzinfo=UTC)
    reference = now - timedelta(minutes=10)
    assert is_stale(reference, ttl_minutes=60, now=now) is False


def test_age_seconds_never_negative_for_future_reference():
    now = datetime(2026, 9, 10, 12, 0, tzinfo=UTC)
    future = now + timedelta(minutes=5)
    assert age_seconds(future, now) == 0.0


def test_age_seconds_computes_elapsed_time():
    now = datetime(2026, 9, 10, 12, 0, tzinfo=UTC)
    reference = now - timedelta(seconds=42)
    assert age_seconds(reference, now) == 42.0
