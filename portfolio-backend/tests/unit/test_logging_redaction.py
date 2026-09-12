from __future__ import annotations

import logging

from app.observability.logging import JsonFormatter, log_event


def _format(record: logging.LogRecord) -> str:
    return JsonFormatter().format(record)


def test_structured_field_with_secret_marker_is_redacted():
    logger = logging.getLogger("test.redaction")
    record = logger.makeRecord("test.redaction", logging.INFO, __file__, 1, "session created", (), None)
    record.fields = {"csrf_token": "not-a-real-secret-value", "user_id": "abc"}
    payload = _format(record)
    assert "not-a-real-secret-value" not in payload
    assert "***redacted***" in payload
    assert '"user_id": "abc"' in payload


def test_message_with_inline_secret_is_redacted():
    logger = logging.getLogger("test.redaction")
    record = logger.makeRecord(
        "test.redaction",
        logging.INFO,
        __file__,
        1,
        "request failed with token=notarealvalueusedintestonly here",
        (),
        None,
    )
    payload = _format(record)
    assert "notarealvalueusedintestonly" not in payload
    assert "token=***redacted***" in payload


def test_log_event_helper_attaches_fields(caplog):
    logger = logging.getLogger("test.redaction.helper")
    with caplog.at_level(logging.INFO, logger="test.redaction.helper"):
        log_event(logger, logging.INFO, "hello", portfolio_id="p1")
    assert caplog.records[0].fields == {"portfolio_id": "p1"}
