import pytest

from app.adapters.calendar_ics import CalendarIcsAdapter
from app.adapters.json_api import JsonApiAdapter
from app.adapters.registry import build_adapter
from app.adapters.rss_atom import RssAtomAdapter


@pytest.mark.parametrize(
    "provider_type,expected_cls",
    [("rss", RssAtomAdapter), ("json_api", JsonApiAdapter), ("calendar_ics", CalendarIcsAdapter)],
)
def test_build_adapter_returns_expected_class(provider_type, expected_cls):
    adapter = build_adapter(provider_type, "prov-1", {})
    assert isinstance(adapter, expected_cls)
    assert adapter.provider_id == "prov-1"


def test_build_adapter_unknown_type_raises():
    with pytest.raises(ValueError, match="no adapter registered"):
        build_adapter("carrier-pigeon", "prov-1", {})
