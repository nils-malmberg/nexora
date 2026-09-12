"""Shared helpers used by every adapter's `normalize()` implementation.

Kept separate from app/pipeline/normalize.py: this module has no DB access
and only does pure, adapter-local transforms (canonical URL, category/kind
clamping, content hash). Asset resolution against the DB happens later, in
the pipeline.
"""

from __future__ import annotations

import hashlib
import re
from datetime import datetime
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

ALLOWED_CATEGORIES = {
    "resultats",
    "dividende",
    "reglementation",
    "operation_titre",
    "gouvernance",
    "marche",
    "macro",
    "autre",
}
ALLOWED_KINDS = {"fact", "synthesis", "prediction"}
ALLOWED_EVENT_STATUSES = {"confirme", "previsionnel", "reporte", "annule", "unknown"}

_TRACKING_PARAM_PREFIXES = ("utm_", "fbclid", "gclid", "mc_cid", "mc_eid")


def canonicalize_url(url: str) -> str:
    parts = urlsplit(url.strip())
    kept_query = [
        (k, v)
        for k, v in parse_qsl(parts.query, keep_blank_values=True)
        if not any(k.lower().startswith(p) for p in _TRACKING_PARAM_PREFIXES)
    ]
    path = parts.path.rstrip("/") or "/"
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), path, urlencode(kept_query), ""))


def normalize_title(title: str) -> str:
    return re.sub(r"\s+", " ", title).strip()


def normalize_category(raw: str | None) -> str:
    if not raw:
        return "autre"
    key = raw.strip().lower().replace(" ", "_").replace("-", "_")
    return key if key in ALLOWED_CATEGORIES else "autre"


def normalize_kind(raw: str | None) -> str:
    if not raw:
        return "fact"
    key = raw.strip().lower()
    return key if key in ALLOWED_KINDS else "fact"


def normalize_event_status(raw: str | None) -> str:
    if not raw:
        return "unknown"
    key = raw.strip().lower()
    return key if key in ALLOWED_EVENT_STATUSES else "unknown"


def compute_content_hash(provider_id: str, canonical_url: str, title: str, event_at: datetime | None) -> str:
    basis = "|".join(
        [
            provider_id,
            canonical_url,
            normalize_title(title).lower(),
            event_at.isoformat() if event_at else "",
        ]
    )
    return hashlib.sha256(basis.encode("utf-8")).hexdigest()


def truncate(text: str | None, max_len: int) -> str | None:
    if text is None:
        return None
    text = re.sub(r"<[^>]+>", " ", text)  # strip any residual HTML tags
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) <= max_len:
        return text or None
    return text[: max_len - 1].rstrip() + "…"
