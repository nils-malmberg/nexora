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
import sys
from datetime import UTC, datetime

_REDACT_SUBSTRINGS = ("authorization", "api_key", "apikey", "token", "password", "secret", "cookie")
_TRUNCATE_KEYS = {"title", "excerpt", "summary", "content", "raw", "body", "raw_meta"}
_TRUNCATE_LEN = 120


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


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
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


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)


def log_event(logger: logging.Logger, level: int, message: str, **fields) -> None:
    logger.log(level, message, extra={"fields": fields})
