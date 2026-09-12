from datetime import UTC, datetime

import pytest

from app.api.bucketing import bucket_label


def test_bucket_label_none_is_unknown():
    assert bucket_label(None, "month") == "unknown"


@pytest.mark.parametrize(
    "granularity,expected",
    [
        ("day", "2026-09-05"),
        ("month", "2026-09"),
        ("quarter", "2026-Q3"),
        ("year", "2026"),
    ],
)
def test_bucket_label_granularities(granularity, expected):
    dt = datetime(2026, 9, 5, 12, 0, tzinfo=UTC)
    assert bucket_label(dt, granularity) == expected


def test_bucket_label_rejects_unknown_granularity():
    with pytest.raises(ValueError):
        bucket_label(datetime(2026, 1, 1, tzinfo=UTC), "fortnight")
