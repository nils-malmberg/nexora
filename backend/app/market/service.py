"""Market data service: the only code that talks to providers on behalf of
the API and the worker. Everything is cache-first —

- a quote is refreshed at most once per `quote_freshness_minutes`, otherwise
  the stored `PricePoint` is served with its age;
- daily history is stored as `OhlcBar` rows and re-fetched at most once per
  refresh interval per instrument (and only for the missing tail/head);
- FX rates are stored as `FxRate` rows, fetched as a whole series at once.

A provider that is rate-limited, down, or circuit-open never breaks a page:
the caller gets the last known data plus an explicit status
(`fresh` | `cached` | `stale` | `unavailable`) and reason.
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import settings
from app.market import registry
from app.market.base import (
    MarketDataError,
    MarketMisconfigured,
    MarketNotFound,
    MarketNotSupported,
    MarketRateLimited,
    MarketUnavailable,
    SearchResult,
)
from app.market.ratelimit import TTLCache
from app.models import FxRate, Instrument, OhlcBar, PositionLot, PricePoint, WatchlistItem
from app.observability.logging import get_logger, log_event
from app.observability.metrics import market_cache_hits_total, market_quote_age_seconds

logger = get_logger(__name__)

_search_cache = TTLCache(ttl_seconds=600)
_history_marks = TTLCache(ttl_seconds=settings.market_refresh_interval_seconds, max_entries=4096)
_fx_marks = TTLCache(ttl_seconds=settings.market_refresh_interval_seconds, max_entries=1024)

# One lock per instrument / FX pair: concurrent requests for the same series
# (a page loads the chart and the indicators at once) serialize on it, so the
# second one reads the rows the first one just stored instead of racing the
# "already fetched" mark and seeing an empty table.
_sync_locks: dict[str, threading.Lock] = {}
_sync_locks_guard = threading.Lock()


def _lock_for(key: str) -> threading.Lock:
    with _sync_locks_guard:
        lock = _sync_locks.get(key)
        if lock is None:
            lock = _sync_locks[key] = threading.Lock()
        return lock


def reset_caches() -> None:
    """Test-only."""
    _search_cache.clear()
    _history_marks.clear()
    _fx_marks.clear()


# ---------------------------------------------------------------------------
# Search + catalog
# ---------------------------------------------------------------------------


@dataclass
class Candidate:
    symbol: str
    name: str
    asset_class: str
    currency: str | None
    exchange: str | None
    provider: str
    provider_symbol: str
    instrument_id: str | None = None
    isin: str | None = None
    in_catalog: bool = False


@dataclass
class SearchOutcome:
    candidates: list[Candidate]
    providers_queried: list[str] = field(default_factory=list)
    provider_errors: dict[str, str] = field(default_factory=dict)


def _candidate_from_instrument(instrument: Instrument) -> Candidate:
    return Candidate(
        symbol=instrument.symbol,
        name=instrument.name,
        asset_class=instrument.asset_class,
        currency=instrument.currency,
        exchange=instrument.exchange,
        provider=instrument.provider or "manual",
        provider_symbol=instrument.provider_symbol or instrument.symbol,
        instrument_id=instrument.id,
        isin=instrument.isin,
        in_catalog=True,
    )


def _handle_provider_error(db: Session, name: str, exc: Exception) -> str:
    """Maps a provider failure to breaker bookkeeping + a short reason."""
    if isinstance(exc, MarketRateLimited):
        if exc.remote:
            registry.record_failure(db, name, "rate limited by provider (HTTP 429)")
        return "rate_limited"
    if isinstance(exc, MarketNotFound):
        return "not_found"
    if isinstance(exc, MarketNotSupported):
        registry.record_failure(db, name, str(exc), open_circuit=False)
        return "not_supported"
    if isinstance(exc, MarketMisconfigured):
        registry.record_failure(db, name, str(exc), open_circuit=False)
        return "misconfigured"
    if isinstance(exc, MarketUnavailable):
        registry.record_failure(db, name, str(exc))
        return "unavailable"
    registry.record_failure(db, name, f"{exc.__class__.__name__}")
    log_event(logger, logging.ERROR, "unexpected market provider error", provider=name, error=str(exc)[:200])
    return "error"


def search(db: Session, user_id: str, query: str, asset_class: str | None = None, limit: int = 10) -> SearchOutcome:
    """Local catalog first (shared + caller's private instruments), then the
    configured providers — each at most once per 10 min for the same query
    thanks to the in-process cache."""
    q = query.strip()
    pattern = f"%{q}%"
    local_query = (
        select(Instrument)
        .where((Instrument.user_id.is_(None)) | (Instrument.user_id == user_id))
        .where((Instrument.symbol.ilike(pattern)) | (Instrument.name.ilike(pattern)) | (Instrument.isin == q.upper()))
        .order_by(Instrument.symbol)
        .limit(limit)
    )
    if asset_class:
        local_query = local_query.where(Instrument.asset_class == asset_class)
    local = [_candidate_from_instrument(i) for i in db.scalars(local_query).all()]
    known = {(c.provider, c.provider_symbol) for c in local}

    outcome = SearchOutcome(candidates=list(local))
    provider_names = registry.configured_provider_names()
    if asset_class == "crypto":
        provider_names = [settings.market_crypto_provider] if settings.market_crypto_provider != "null" else []
    elif asset_class in ("action", "etf", "indice", "devise"):
        provider_names = [settings.market_equity_provider] if settings.market_equity_provider != "null" else []
    elif asset_class == "actif_prive":
        provider_names = []

    for name in provider_names:
        cache_key = (name, q.lower(), limit)
        cached = _search_cache.get(cache_key)
        if cached is not None:
            market_cache_hits_total.labels(kind="search").inc()
            results = cached
        else:
            if not registry.circuit_allows(db, name):
                outcome.provider_errors[name] = "circuit_open"
                continue
            provider = registry.build_provider(name)
            try:
                results = provider.search(q, limit=limit)
                registry.record_success(db, name)
                _search_cache.set(cache_key, results)
            except MarketDataError as exc:
                outcome.provider_errors[name] = _handle_provider_error(db, name, exc)
                continue
        outcome.providers_queried.append(name)
        for r in results:
            if (r.provider, r.provider_symbol) in known:
                continue
            if asset_class and r.asset_class != asset_class:
                continue
            existing = db.scalars(
                select(Instrument).where(
                    Instrument.provider == r.provider, Instrument.provider_symbol == r.provider_symbol
                )
            ).first()
            known.add((r.provider, r.provider_symbol))
            if existing is not None:
                outcome.candidates.append(_candidate_from_instrument(existing))
            else:
                outcome.candidates.append(
                    Candidate(
                        symbol=r.symbol,
                        name=r.name,
                        asset_class=r.asset_class,
                        currency=r.currency,
                        exchange=r.exchange,
                        provider=r.provider,
                        provider_symbol=r.provider_symbol,
                        isin=r.isin,
                    )
                )
    db.commit()
    return outcome


def ensure_catalog_instrument(
    db: Session,
    *,
    provider: str,
    provider_symbol: str,
    symbol: str,
    name: str,
    asset_class: str,
    currency: str | None,
    exchange: str | None = None,
    isin: str | None = None,
) -> tuple[Instrument, str | None]:
    """Get-or-create a shared catalog row. When the currency is unknown (Yahoo
    search results carry none) a single quote call fills it in — and stores
    that first price while we're at it. Returns (instrument, warning)."""
    existing = db.scalars(
        select(Instrument).where(Instrument.provider == provider, Instrument.provider_symbol == provider_symbol)
    ).first()
    if existing is not None:
        return existing, None

    warning = None
    quote = None
    if provider not in ("manual", "null"):
        if registry.circuit_allows(db, provider):
            try:
                quote = registry.build_provider(provider).quote(provider_symbol)
                registry.record_success(db, provider)
            except MarketDataError as exc:
                warning = _handle_provider_error(db, provider, exc)
        else:
            warning = "circuit_open"
    if quote is not None:
        currency = quote.currency
        exchange = exchange or quote.exchange
    if not currency:
        raise ValueError("currency unknown: provider unavailable and no currency supplied")

    instrument = Instrument(
        user_id=None,
        symbol=symbol.upper()[:32],
        name=name[:200],
        asset_class=asset_class,
        isin=isin,
        exchange=exchange,
        currency=currency.upper(),
        provider=provider,
        provider_symbol=provider_symbol,
    )
    db.add(instrument)
    db.flush()
    if quote is not None:
        db.add(
            PricePoint(
                instrument_id=instrument.id,
                as_of=quote.as_of,
                price=quote.price,
                currency=quote.currency,
                source=quote.source,
                is_delayed=quote.is_delayed,
            )
        )
    return instrument, warning


# ---------------------------------------------------------------------------
# Quotes
# ---------------------------------------------------------------------------


@dataclass
class QuoteView:
    price: PricePoint | None
    status: str  # fresh | cached | stale | unavailable
    reason: str | None = None
    provider: str | None = None
    license_note: str | None = None
    attribution: str | None = None
    previous_close: Decimal | None = None


def latest_price_point(db: Session, instrument_id: str) -> PricePoint | None:
    return db.scalars(
        select(PricePoint).where(PricePoint.instrument_id == instrument_id).order_by(PricePoint.as_of.desc()).limit(1)
    ).first()


def refresh_quote(db: Session, instrument: Instrument, *, force: bool = False) -> QuoteView:
    latest = latest_price_point(db, instrument.id)
    now = datetime.now(UTC)
    provider_name = instrument.provider if instrument.user_id is None else None
    if provider_name in (None, "manual", "null"):
        status = "cached" if latest is not None else "unavailable"
        return QuoteView(price=latest, status=status, reason=None if latest else "no_live_source", provider="manual")

    freshness = timedelta(minutes=settings.quote_freshness_minutes)
    if latest is not None and latest.source == provider_name and not force and (now - latest.collected_at) < freshness:
        market_cache_hits_total.labels(kind="quote").inc()
        return _quote_view(instrument, latest, "fresh", provider_name)

    if not registry.circuit_allows(db, provider_name):
        return _quote_view(instrument, latest, "stale" if latest else "unavailable", provider_name, "circuit_open")

    provider = registry.build_provider(provider_name)
    try:
        quote = provider.quote(instrument.provider_symbol or instrument.symbol)
    except MarketDataError as exc:
        reason = _handle_provider_error(db, provider_name, exc)
        db.commit()
        return _quote_view(instrument, latest, "stale" if latest else "unavailable", provider_name, reason)

    registry.record_success(db, provider_name)
    if quote is None:
        db.commit()
        return _quote_view(instrument, latest, "stale" if latest else "unavailable", provider_name, "no_data")

    if latest is not None and latest.as_of == quote.as_of and latest.source == quote.source:
        latest.collected_at = now  # same tick, just observed again: bump freshness, no duplicate row
        point = latest
    else:
        point = PricePoint(
            instrument_id=instrument.id,
            as_of=quote.as_of,
            price=quote.price,
            currency=quote.currency,
            source=quote.source,
            is_delayed=quote.is_delayed,
            collected_at=now,
        )
        db.add(point)
    db.commit()
    view = _quote_view(instrument, point, "fresh", provider_name)
    view.previous_close = quote.previous_close
    return view


def _quote_view(
    instrument: Instrument, point: PricePoint | None, status: str, provider_name: str, reason: str | None = None
) -> QuoteView:
    caps = registry.build_provider(provider_name).capabilities
    if point is not None:
        market_quote_age_seconds.labels(instrument_id=instrument.id).set(
            (datetime.now(UTC) - point.as_of).total_seconds()
        )
    return QuoteView(
        price=point,
        status=status,
        reason=reason,
        provider=provider_name,
        license_note=caps.license_note or None,
        attribution=caps.attribution or None,
    )


# ---------------------------------------------------------------------------
# History (daily bars)
# ---------------------------------------------------------------------------


@dataclass
class HistoryView:
    bars: list[OhlcBar]
    has_ohlc: bool
    source: str | None
    status: str  # fresh | cached | stale | unavailable
    reason: str | None = None
    license_note: str | None = None
    attribution: str | None = None


def _day(dt: datetime) -> datetime:
    return dt.astimezone(UTC).replace(hour=0, minute=0, second=0, microsecond=0)


def stored_bars(db: Session, instrument_id: str, start: datetime, end: datetime) -> list[OhlcBar]:
    return list(
        db.scalars(
            select(OhlcBar)
            .where(OhlcBar.instrument_id == instrument_id, OhlcBar.as_of >= start, OhlcBar.as_of <= end)
            .order_by(OhlcBar.as_of)
        ).all()
    )


def sync_history(db: Session, instrument: Instrument, start: datetime, end: datetime) -> tuple[int, str | None]:
    """Fetches bars for [start, end] from the instrument's provider and
    upserts them. Returns (bars written, error reason)."""
    provider_name = instrument.provider if instrument.user_id is None else None
    if provider_name in (None, "manual", "null"):
        return 0, "no_live_source"
    if not registry.circuit_allows(db, provider_name):
        return 0, "circuit_open"
    provider = registry.build_provider(provider_name)
    try:
        result = provider.history(instrument.provider_symbol or instrument.symbol, start, end)
    except MarketDataError as exc:
        reason = _handle_provider_error(db, provider_name, exc)
        db.commit()
        return 0, reason
    registry.record_success(db, provider_name)

    existing = {
        b.as_of: b
        for b in stored_bars(db, instrument.id, _day(start) - timedelta(days=1), _day(end) + timedelta(days=1))
    }
    written = 0
    for bar in result.bars:
        key = _day(bar.as_of)
        row = existing.get(key)
        if row is None:
            row = OhlcBar(
                instrument_id=instrument.id, interval="1d", as_of=key, currency=result.currency, source=result.source
            )
            db.add(row)
            existing[key] = row
        row.open, row.high, row.low, row.close, row.volume = bar.open, bar.high, bar.low, bar.close, bar.volume
        row.collected_at = datetime.now(UTC)
        written += 1
    db.commit()
    return written, None


def get_history(db: Session, instrument: Instrument, start: datetime, end: datetime) -> HistoryView:
    """Cache-first daily history. A provider call happens only when the
    stored range doesn't cover the request (no bars, missing head) or the
    tail is older than a day — and at most once per refresh interval per
    (instrument, start) even then."""
    start, end = _day(start), _day(end)
    provider_name = instrument.provider if instrument.user_id is None else None
    live = provider_name not in (None, "manual", "null")

    status, reason = "cached", None
    if live:
        with _lock_for(f"history:{instrument.id}"):
            bars = stored_bars(db, instrument.id, start, end)
            mark_key = (instrument.id, start.date().isoformat())
            needs_head = not bars or (bars[0].as_of - start).days > 7
            needs_tail = not bars or (end - bars[-1].as_of).days > 1
            if (needs_head or needs_tail) and _history_marks.get(mark_key) is None:
                _history_marks.set(mark_key, True)
                fetch_start = start if needs_head else max(start, bars[-1].as_of - timedelta(days=7))
                written, reason = sync_history(db, instrument, fetch_start, end)
                if reason is None:
                    status = "fresh"
                    bars = stored_bars(db, instrument.id, start, end)
                else:
                    status = "stale" if bars else "unavailable"
            elif not (needs_head or needs_tail):
                market_cache_hits_total.labels(kind="history").inc()
    else:
        bars = stored_bars(db, instrument.id, start, end)
        if not bars:
            status, reason = "unavailable", "no_live_source"

    caps = registry.build_provider(provider_name).capabilities if live else None
    has_ohlc = bool(bars) and all(b.open is not None for b in bars)
    return HistoryView(
        bars=bars,
        has_ohlc=has_ohlc,
        source=bars[-1].source if bars else None,
        status=status,
        reason=reason,
        license_note=caps.license_note if caps else None,
        attribution=caps.attribution if caps else None,
    )


# ---------------------------------------------------------------------------
# FX
# ---------------------------------------------------------------------------


def stored_fx_rate(db: Session, base: str, quote: str, on: datetime) -> FxRate | None:
    """Most recent stored rate at or before `on` (within 10 days — rates are
    business-daily, so a weekend/holiday falls back to the last fixing)."""
    return db.scalars(
        select(FxRate)
        .where(FxRate.base == base, FxRate.quote == quote, FxRate.as_of <= on, FxRate.as_of >= on - timedelta(days=10))
        .order_by(FxRate.as_of.desc())
        .limit(1)
    ).first()


def ensure_fx_series(db: Session, base: str, quote: str, start: datetime, end: datetime) -> str | None:
    """Fetches (once per interval) the daily series for the pair over the
    range and stores what's missing. Returns an error reason or None."""
    if base == quote:
        return None
    provider = registry.fx_provider()
    if provider.name.startswith("null"):
        return "fx_disabled"
    key = (base, quote, _day(start).date().isoformat(), _day(end).date().isoformat())
    with _lock_for(f"fx:{base}:{quote}"):
        if _fx_marks.get(key) is not None:
            return None
        _fx_marks.set(key, True)
        if not registry.circuit_allows(db, provider.name):
            return "circuit_open"
        try:
            series = provider.series(base, quote, _day(start), _day(end))
            registry.record_success(db, provider.name)
        except MarketDataError as exc:
            reason = _handle_provider_error(db, provider.name, exc)
            db.commit()
            return reason
        existing = {
            r.as_of
            for r in db.scalars(
                select(FxRate).where(
                    FxRate.base == base, FxRate.quote == quote, FxRate.as_of >= _day(start), FxRate.as_of <= _day(end)
                )
            )
        }
        for day, rate in series.items():
            if day not in existing:
                db.add(FxRate(base=base, quote=quote, as_of=day, rate=rate, source=provider.name))
        db.commit()
        return None


def get_fx_rate(db: Session, base: str, quote: str, on: datetime | None = None) -> FxRate | None:
    """Rate for converting 1 `base` into `quote` as of `on` (default now).
    Cache-first; a miss triggers one `latest` call (today) or one series
    fetch of the surrounding fortnight (historical date)."""
    if base == quote:
        return FxRate(base=base, quote=quote, as_of=_day(on or datetime.now(UTC)), rate=Decimal("1"), source="identity")
    on = on or datetime.now(UTC)
    on_day = _day(on)
    today = _day(datetime.now(UTC))
    cached = stored_fx_rate(db, base, quote, on_day)
    is_today = on_day >= today
    if cached is not None and (not is_today or (today - cached.as_of).days <= 3):
        return cached

    provider = registry.fx_provider()
    if provider.name.startswith("null"):
        return cached
    if is_today:
        key = (base, quote, "latest")
        if _fx_marks.get(key) is not None:
            return cached
        _fx_marks.set(key, True)
        if not registry.circuit_allows(db, provider.name):
            return cached
        try:
            day, rates = provider.latest(base, [quote])
            registry.record_success(db, provider.name)
        except MarketDataError as exc:
            _handle_provider_error(db, provider.name, exc)
            db.commit()
            return cached
        rate = rates.get(quote)
        if rate is None:
            return cached
        row = db.scalars(select(FxRate).where(FxRate.base == base, FxRate.quote == quote, FxRate.as_of == day)).first()
        if row is None:
            row = FxRate(base=base, quote=quote, as_of=day, rate=rate, source=provider.name)
            db.add(row)
        db.commit()
        return row
    ensure_fx_series(db, base, quote, on_day - timedelta(days=14), on_day)
    return stored_fx_rate(db, base, quote, on_day)


# ---------------------------------------------------------------------------
# Worker: periodic refresh of everything users actually track
# ---------------------------------------------------------------------------


def tracked_instrument_ids(db: Session) -> list[str]:
    held = select(PositionLot.instrument_id).where(PositionLot.quantity_remaining > 0)
    watched = select(WatchlistItem.instrument_id)
    ids = {row[0] for row in db.execute(held)} | {row[0] for row in db.execute(watched)}
    return sorted(ids)


def refresh_tracked(db: Session) -> dict:
    """One pass over held + watched catalog instruments: refresh the quote and
    top up the daily history. Sequential, budget-aware (a refused token just
    leaves that instrument for the next cycle) — never a burst."""
    summary = {"instruments": 0, "quotes_fresh": 0, "quotes_skipped": 0, "history_bars": 0, "errors": 0}
    for instrument_id in tracked_instrument_ids(db):
        instrument = db.get(Instrument, instrument_id)
        if instrument is None or instrument.user_id is not None or instrument.provider in (None, "manual", "null"):
            continue
        summary["instruments"] += 1
        view = refresh_quote(db, instrument)
        if view.status == "fresh":
            summary["quotes_fresh"] += 1
        else:
            summary["quotes_skipped"] += 1
            if view.reason not in (None, "rate_limited", "circuit_open"):
                summary["errors"] += 1
        latest_bar = db.scalar(select(func.max(OhlcBar.as_of)).where(OhlcBar.instrument_id == instrument.id))
        now = datetime.now(UTC)
        if latest_bar is None or (now - latest_bar).days >= 1:
            start = (latest_bar - timedelta(days=7)) if latest_bar else now - timedelta(days=365)
            written, reason = sync_history(db, instrument, start, now)
            summary["history_bars"] += written
            if reason not in (None, "rate_limited", "circuit_open"):
                summary["errors"] += 1
    return summary


__all__ = [
    "Candidate",
    "SearchOutcome",
    "SearchResult",
    "QuoteView",
    "HistoryView",
    "search",
    "ensure_catalog_instrument",
    "refresh_quote",
    "get_history",
    "sync_history",
    "get_fx_rate",
    "ensure_fx_series",
    "refresh_tracked",
    "reset_caches",
]
