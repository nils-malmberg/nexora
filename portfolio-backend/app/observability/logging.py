"""Structured JSON logging with secret redaction — same convention as the
News & Events module (specs/SECURITY.md: no secret/personal data in logs)."""

from __future__ import annotations

import json
import logging
import re
import sys
from datetime import UTC, datetime

_REDACT_SUBSTRINGS = ("authorization", "api_key", "apikey", "token", "password", "secret", "cookie", "csrf")

_MESSAGE_SECRET_RE = re.compile(r"(?i)\b(" + "|".join(_REDACT_SUBSTRINGS) + r")=([^&\s\"']+)")


def _sanitize(fields: dict) -> dict:
    sanitized: dict = {}
    for key, value in fields.items():
        if any(marker in key.lower() for marker in _REDACT_SUBSTRINGS):
            sanitized[key] = "***redacted***"
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


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)


def log_event(logger: logging.Logger, level: int, message: str, **fields) -> None:
    logger.log(level, message, extra={"fields": fields})
