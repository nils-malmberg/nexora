from datetime import UTC

from app.utils.timeparse import parse_iso8601, parse_rfc2822, struct_time_to_utc


def test_parse_iso8601_with_z_suffix():
    dt = parse_iso8601("2026-09-01T07:00:00Z")
    assert dt is not None
    assert dt.tzinfo is not None
    assert dt.utcoffset().total_seconds() == 0
    assert dt.hour == 7


def test_parse_iso8601_with_explicit_offset_normalizes_to_utc():
    dt = parse_iso8601("2026-09-01T09:00:00+02:00")
    assert dt is not None
    assert dt.astimezone(UTC).hour == 7


def test_parse_iso8601_unknown_stays_unknown():
    assert parse_iso8601(None) is None
    assert parse_iso8601("") is None
    assert parse_iso8601("not-a-date") is None


def test_parse_rfc2822():
    dt = parse_rfc2822("Tue, 01 Sep 2026 07:00:00 +0000")
    assert dt is not None
    assert dt.tzinfo is not None
    assert dt.hour == 7


def test_parse_rfc2822_unknown_stays_unknown():
    assert parse_rfc2822(None) is None
    assert parse_rfc2822("garbage") is None


def test_struct_time_to_utc_none_stays_none():
    assert struct_time_to_utc(None) is None


def test_struct_time_to_utc_converts():
    import time

    struct = time.strptime("2026-09-01 07:00:00", "%Y-%m-%d %H:%M:%S")
    dt = struct_time_to_utc(struct)
    assert dt.year == 2026 and dt.hour == 7
    assert dt.tzinfo is not None
