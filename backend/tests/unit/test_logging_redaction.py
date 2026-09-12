import json
import logging

from app.observability.logging import JsonFormatter, log_event


def _format_record(**fields) -> dict:
    logger = logging.getLogger("test-redaction")
    record = logger.makeRecord(logger.name, logging.INFO, __file__, 0, "event", (), None)
    record.fields = fields
    return json.loads(JsonFormatter().format(record))


def test_secret_like_fields_are_redacted():
    payload = _format_record(api_key="sk-super-secret", Authorization="Bearer abc", plain="ok")
    assert payload["api_key"] == "***redacted***"
    assert payload["Authorization"] == "***redacted***"
    assert payload["plain"] == "ok"


def test_licensed_content_fields_are_truncated():
    long_title = "x" * 500
    payload = _format_record(title=long_title)
    assert len(payload["title"]) < 500
    assert payload["title"].endswith("…")


def test_log_event_helper_produces_valid_json(capsys):
    from app.observability.logging import configure_logging, get_logger

    root = logging.getLogger()
    previous_handlers, previous_level = list(root.handlers), root.level
    try:
        configure_logging("INFO")
        logger = get_logger("test-redaction-integration")
        log_event(logger, logging.INFO, "hello", api_key="secret-value", provider_id="prov-1")
        captured = capsys.readouterr()
        line = json.loads(captured.out.strip().splitlines()[-1])
        assert line["message"] == "hello"
        assert line["api_key"] == "***redacted***"
        assert line["provider_id"] == "prov-1"
    finally:
        root.handlers = previous_handlers
        root.setLevel(previous_level)
