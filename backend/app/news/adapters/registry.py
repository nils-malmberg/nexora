from __future__ import annotations

from app.news.adapters.base import ProviderAdapter
from app.news.adapters.calendar_ics import CalendarIcsAdapter
from app.news.adapters.json_api import JsonApiAdapter
from app.news.adapters.rss_atom import RssAtomAdapter

ADAPTER_CLASSES: dict[str, type[ProviderAdapter]] = {
    "rss": RssAtomAdapter,
    "json_api": JsonApiAdapter,
    "calendar_ics": CalendarIcsAdapter,
}


def build_adapter(provider_type: str, provider_id: str, provider_config: dict) -> ProviderAdapter:
    try:
        adapter_cls = ADAPTER_CLASSES[provider_type]
    except KeyError as exc:
        raise ValueError(f"no adapter registered for provider type '{provider_type}'") from exc
    return adapter_cls(provider_id=provider_id, provider_config=provider_config)
