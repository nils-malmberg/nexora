"""Structured JSON logging with automatic secret/content redaction.

Every ingestion log line should carry `ingestion_run_id` so runs can be
correlated end to end (specs/NEWS_AND_EVENTS.md: "Corréler les logs par
ingestion_run_id"). Anything that looks like a credential is redacted, and
licensed content fields (title/excerpt/summary/raw body) are truncated so
logs never become a de facto copy of the source.
"""

from __future__ import annotations

import json
import logging
import re
import sys
from datetime import UTC, datetime

_REDACT_SUBSTRINGS = ("authorization", "api_key", "apikey", "token", "password", "secret", "cookie", "csrf")
_TRUNCATE_KEYS = {"title", "excerpt", "summary", "content", "raw", "body", "raw_meta"}
_TRUNCATE_LEN = 120

# Query-param secrets (e.g. Finnhub's `?token=...`) end up in the URL a
# library like httpx logs by default - `_sanitize()` below only covers our
# own structured `fields`, not a raw message string, so this is a second,
# independent layer scrubbing any `key=value` pair whose key looks like a
# credential, wherever it appears in the rendered message.
_MESSAGE_SECRET_RE = re.compile(
    r"(?i)\b(" + "|".join(_REDACT_SUBSTRINGS) + r")=([^&\s\"']+)",
)


def _sanitize(fields: dict) -> dict:
    sanitized: dict = {}
    for key, value in fields.items():
        lower = key.lower()
        if any(marker in lower for marker in _REDACT_SUBSTRINGS):
            sanitized[key] = "***redacted***"
        elif lower in _TRUNCATE_KEYS and isinstance(value, str) and len(value) > _TRUNCATE_LEN:
            sanitized[key] = value[:_TRUNCATE_LEN] + "…"
        else:
            sanitized[key] = value
    return sanitized


def _sanitize_message(message: str) -> str:
    return _MESSAGE_SECRET_RE.sub(lambda m: f"{m.group(1)}=***redacted***", message)


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": _sanitize_message(record.getMessage()),
        }
        fields = getattr(record, "fields", None)
        if fields:
            payload.update(_sanitize(fields))
        return json.dumps(payload, default=str)


def configure_logging(level: str = "INFO") -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level)
    # httpx/httpcore log every request at INFO, including the full URL -
    # for query-param auth (see app/adapters/json_api.py) that URL contains
    # the resolved secret. _sanitize_message() is a second safety net, but
    # there is no reason to keep this noisy, redundant per-request logging
    # at all: our own ingestion logs already capture what matters.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)


def log_event(logger: logging.Logger, level: int, message: str, **fields) -> None:
    logger.log(level, message, extra={"fields": fields})
