from datetime import UTC, datetime

from app.news.adapters.common import (
    canonicalize_url,
    compute_content_hash,
    normalize_category,
    normalize_event_status,
    normalize_kind,
    normalize_title,
    resolve_query_param_templates,
    truncate,
)


def test_canonicalize_url_strips_tracking_params_and_trailing_slash():
    url = "https://Example.com/News/Item/?utm_source=x&utm_medium=y&id=42&"
    assert canonicalize_url(url) == "https://example.com/News/Item?id=42"


def test_canonicalize_url_is_stable_regardless_of_tracking_params():
    a = canonicalize_url("https://example.com/a?utm_source=twitter")
    b = canonicalize_url("https://example.com/a?utm_source=facebook")
    assert a == b


def test_normalize_title_collapses_whitespace():
    assert normalize_title("  hello   world\n") == "hello world"


def test_normalize_category_defaults_to_autre():
    assert normalize_category(None) == "autre"
    assert normalize_category("unknown-thing") == "autre"
    assert normalize_category("Resultats") == "resultats"
    assert normalize_category("operation-titre") == "operation_titre"


def test_normalize_kind_defaults_to_fact():
    assert normalize_kind(None) == "fact"
    assert normalize_kind("bogus") == "fact"
    assert normalize_kind("PREDICTION") == "prediction"


def test_normalize_event_status_defaults_to_unknown():
    assert normalize_event_status(None) == "unknown"
    assert normalize_event_status("weird") == "unknown"
    assert normalize_event_status("confirme") == "confirme"


def test_compute_content_hash_stable_for_same_inputs():
    event_at = datetime(2026, 9, 1, tzinfo=UTC)
    h1 = compute_content_hash("provider-a", "https://x.test/1", "Title", event_at)
    h2 = compute_content_hash("provider-a", "https://x.test/1", "Title", event_at)
    assert h1 == h2


def test_compute_content_hash_differs_for_different_provider():
    event_at = datetime(2026, 9, 1, tzinfo=UTC)
    h1 = compute_content_hash("provider-a", "https://x.test/1", "Title", event_at)
    h2 = compute_content_hash("provider-b", "https://x.test/1", "Title", event_at)
    assert h1 != h2


def test_truncate_strips_html_and_shortens():
    text = "<p>" + ("word " * 200) + "</p>"
    result = truncate(text, 50)
    assert result is not None
    assert len(result) <= 50
    assert "<p>" not in result


def test_truncate_none_stays_none():
    assert truncate(None, 100) is None


def test_resolve_query_param_templates_today_and_offset():
    now = datetime(2026, 9, 12, 15, 0, tzinfo=UTC)
    resolved = resolve_query_param_templates({"to": "{{today}}", "from": "{{today-30d}}"}, now=now)
    assert resolved == {"to": "2026-09-12", "from": "2026-08-13"}


def test_resolve_query_param_templates_leaves_non_template_values_untouched():
    now = datetime(2026, 9, 12, tzinfo=UTC)
    resolved = resolve_query_param_templates({"symbol": "AAPL", "limit": 50}, now=now)
    assert resolved == {"symbol": "AAPL", "limit": 50}


def test_resolve_query_param_templates_ignores_lookalike_strings():
    now = datetime(2026, 9, 12, tzinfo=UTC)
    resolved = resolve_query_param_templates({"q": "today's news {{not-a-token}}"}, now=now)
    assert resolved == {"q": "today's news {{not-a-token}}"}
