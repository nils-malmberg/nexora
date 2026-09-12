"""Opaque cursor pagination: base64("<iso-timestamp>|<id>"). Same convention
as the News & Events module's API (see specs/API_SPEC.md: "Pagination
curseur")."""

from __future__ import annotations

import base64
import binascii
from datetime import datetime

from fastapi import HTTPException


def encode_cursor(sort_key: datetime, id_: str) -> str:
    raw = f"{sort_key.isoformat()}|{id_}"
    return base64.urlsafe_b64encode(raw.encode("utf-8")).decode("ascii")


def decode_cursor(cursor: str) -> tuple[datetime, str]:
    try:
        raw = base64.urlsafe_b64decode(cursor.encode("ascii")).decode("utf-8")
        iso, id_ = raw.rsplit("|", 1)
        return datetime.fromisoformat(iso), id_
    except (ValueError, binascii.Error) as exc:
        raise HTTPException(status_code=400, detail="invalid pagination cursor") from exc


def clamp_page_size(requested: int | None, default: int, maximum: int) -> int:
    if requested is None:
        return default
    return max(1, min(requested, maximum))
