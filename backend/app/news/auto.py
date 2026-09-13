"""Automatic company news for catalog instruments.

The generic pipeline (app/news/pipeline) only fetches feeds that were
configured by hand. This module makes news appear without configuration:
every shared equity/ETF instrument gets a Finnhub `company-news` feed
(when `FINNHUB_API_KEY` is set), created lazily the first time someone opens
its news, refreshed on demand at most once per `news_freshness_minutes`, and
kept fresh by the worker only for instruments that are held or watched.

Quota discipline (Finnhub free tier ~60 calls/min): one request per
instrument per refresh, every outbound call takes a token from the shared
`finnhub` bucket (app/market/http.py), and a failing key or a rate limit
opens the provider's circuit breaker like any other source.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.market.http import bucket_for
from app.market.ratelimit import TTLCache
from app.market.service import tracked_instrument_ids
from app.models import Instrument, NewsItem, NewsItemAsset, Provider, ProviderFeed
from app.news.pipeline.ingest import run_provider

AUTO_PROVIDER_NAME = "finnhub-company-news"
COMPANY_NEWS_URL = "https://finnhub.io/api/v1/company-news"
AUTO_ASSET_CLASSES = ("action", "etf")

_refresh_marks = TTLCache(ttl_seconds=settings.news_freshness_minutes * 60, max_entries=4096)


def reset_marks() -> None:
    """Test-only."""
    _refresh_marks.clear()


def is_configured() -> bool:
    return settings.news_auto_company_news and bool(os.environ.get(settings.finnhub_api_key_env_var))


def eligible(instrument: Instrument) -> bool:
    return instrument.user_id is None and instrument.asset_class in AUTO_ASSET_CLASSES


def _provider(db: Session) -> Provider:
    provider = db.scalar(select(Provider).where(Provider.name == AUTO_PROVIDER_NAME))
    if provider is None:
        provider = Provider(
            name=AUTO_PROVIDER_NAME,
            type="json_api",
            config={
                "content_type": "news",
                "base_confidence": 0.6,
                "timestamp_format": "unix_seconds",
                "mapping": {
                    "external_id": "id",
                    "title": "headline",
                    "url": "url",
                    "summary": "summary",
                    "published_at": "datetime",
                    "asset_symbol": "related",
                },
                "pagination": {"style": "none"},
                # Finnhub's OpenAPI spec declares `token` as a query parameter.
                "auth": {"in": "query", "param": "token", "env_var": settings.finnhub_api_key_env_var},
                "rate_limit_per_minute": settings.finnhub_rate_limit_per_minute,
            },
            license_note=(
                "Finnhub company-news (offre gratuite, clé personnelle) - usage personnel/non commercial, "
                "~60 appels/minute ; CGU à vérifier sur finnhub.io. Feeds créés automatiquement par instrument."
            ),
        )
        db.add(provider)
        db.flush()
    return provider


def ensure_feed(db: Session, instrument: Instrument) -> ProviderFeed | None:
    """Get-or-create the company-news feed of one catalog instrument."""
    if not eligible(instrument):
        return None
    provider = _provider(db)
    feed = db.scalar(
        select(ProviderFeed).where(ProviderFeed.provider_id == provider.id, ProviderFeed.instrument_id == instrument.id)
    )
    if feed is None:
        symbol = instrument.provider_symbol or instrument.symbol
        feed = ProviderFeed(
            provider_id=provider.id,
            instrument_id=instrument.id,
            url=COMPANY_NEWS_URL,
            extra_config={
                "instrument_id": instrument.id,
                "query_params": {"symbol": symbol, "from": "{{today-30d}}", "to": "{{today}}"},
            },
        )
        db.add(feed)
        db.flush()
    return feed


@dataclass
class RefreshOutcome:
    status: str  # refreshed | cached | not_configured | not_eligible | rate_limited | provider_disabled | failed
    detail: str | None = None
    items_total: int = 0
    run_status: str | None = None
    error_code: str | None = None


def _count_items(db: Session, instrument_id: str) -> int:
    return len(db.scalars(select(NewsItemAsset.id).where(NewsItemAsset.instrument_id == instrument_id)).all())


def refresh_instrument_news(db: Session, instrument: Instrument, *, force: bool = False) -> RefreshOutcome:
    """On-demand refresh of one instrument's company news: one Finnhub
    request at most per freshness window (per process), never a loop."""
    if not eligible(instrument):
        return RefreshOutcome("not_eligible", "actualités automatiques réservées aux actions/ETF du catalogue")
    if not is_configured():
        return RefreshOutcome(
            "not_configured",
            f"définissez {settings.finnhub_api_key_env_var} (clé gratuite sur finnhub.io) "
            "pour les actualités par société",
            _count_items(db, instrument.id),
        )
    if not force and _refresh_marks.get(instrument.id) is not None:
        return RefreshOutcome("cached", None, _count_items(db, instrument.id))
    feed = ensure_feed(db, instrument)
    provider = feed.provider if feed else _provider(db)
    db.commit()
    if not provider.enabled:
        return RefreshOutcome(
            "provider_disabled",
            "source d'actualités désactivée (voir Paramètres › Administration)",
            _count_items(db, instrument.id),
        )
    if not bucket_for("finnhub").take():
        return RefreshOutcome(
            "rate_limited",
            "budget de requêtes Finnhub épuisé, réessayez dans une minute",
            _count_items(db, instrument.id),
        )
    _refresh_marks.set(instrument.id, True)
    run = run_provider(db, provider, feeds=[feed])
    status = "refreshed" if run.status in ("success", "partial") else "failed"
    detail = None
    if status == "failed":
        detail = {
            "circuit_open": "source en pause après des échecs répétés",
            "all_feeds_failed": "Finnhub n'a pas répondu (clé invalide, quota ou panne) - voir le journal",
            "provider_disabled": "source désactivée",
        }.get(run.error_code or "", run.error_code)
    return RefreshOutcome(status, detail, _count_items(db, instrument.id), run.status, run.error_code)


def ensure_feeds_for_tracked(db: Session) -> int:
    """Worker hook: every held/watched catalog equity gets its feed, so news
    starts flowing without anyone opening the news tab first. Returns the
    number of feeds created."""
    if not is_configured():
        return 0
    created = 0
    for instrument_id in tracked_instrument_ids(db):
        instrument = db.get(Instrument, instrument_id)
        if instrument is None or not eligible(instrument):
            continue
        provider = _provider(db)
        exists = db.scalar(
            select(ProviderFeed.id).where(
                ProviderFeed.provider_id == provider.id, ProviderFeed.instrument_id == instrument.id
            )
        )
        if exists is None:
            ensure_feed(db, instrument)
            created += 1
    db.commit()
    return created


def feeds_to_refresh(db: Session, provider: Provider) -> list[ProviderFeed] | None:
    """For the automatic provider, only feeds of instruments somebody holds or
    watches (an instrument browsed once must not cost a request every 15
    minutes forever); every other provider runs all its feeds."""
    if provider.name != AUTO_PROVIDER_NAME:
        return None
    tracked = set(tracked_instrument_ids(db))
    return [f for f in provider.feeds if f.instrument_id in tracked]


def latest_collection(db: Session, instrument_id: str) -> datetime | None:
    return db.scalar(
        select(NewsItem.collected_at)
        .join(NewsItemAsset, NewsItemAsset.news_item_id == NewsItem.id)
        .where(NewsItemAsset.instrument_id == instrument_id)
        .order_by(NewsItem.collected_at.desc())
        .limit(1)
    )


def is_fresh(db: Session, instrument_id: str) -> bool:
    latest = latest_collection(db, instrument_id)
    return latest is not None and datetime.now(UTC) - latest < timedelta(minutes=settings.news_freshness_minutes)
