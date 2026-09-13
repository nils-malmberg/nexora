from __future__ import annotations

from datetime import UTC, datetime

import pytest
from fastapi import HTTPException

from app.api.pagination import clamp_page_size, decode_cursor, encode_cursor


def test_cursor_roundtrip():
    ts = datetime(2026, 1, 1, tzinfo=UTC)
    cursor = encode_cursor(ts, "abc123")
    decoded_ts, decoded_id = decode_cursor(cursor)
    assert decoded_ts == ts
    assert decoded_id == "abc123"


def test_decode_invalid_cursor_raises_400():
    with pytest.raises(HTTPException) as exc_info:
        decode_cursor("not-a-valid-cursor!!")
    assert exc_info.value.status_code == 400


def test_clamp_page_size_defaults_when_none():
    assert clamp_page_size(None, default=20, maximum=100) == 20


def test_clamp_page_size_clamps_to_maximum():
    assert clamp_page_size(500, default=20, maximum=100) == 100


def test_clamp_page_size_floors_at_one():
    assert clamp_page_size(-5, default=20, maximum=100) == 1
