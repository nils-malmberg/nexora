"""Read-only provider overview for every signed-in user: which market/FX
sources are configured and healthy (with their attribution and license
notes, as specs/DATA_SOURCES.md requires them to be shown), which news
sources exist, and whether the experimental prediction module is switched on."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.config import settings
from app.market import registry
from app.models import Provider, User
from app.schemas.providers import MarketProviderPublicOut, ProvidersOverviewOut, ProviderStatusOut

router = APIRouter(prefix="/api/v1/providers", tags=["providers"])


def _market_entry(db: Session, name: str, role: str) -> MarketProviderPublicOut:
    if role == "fx":
        provider = registry.fx_provider()
        caps = {"fx": True}
        attribution, license_note = provider.attribution, provider.license_note
        health = provider.health()
    else:
        provider = registry.build_provider(name)
        c = provider.capabilities
        caps = {
            "search": c.search,
            "quote": c.quote,
            "history": c.history,
            "ohlc": c.ohlc,
            "asset_classes": list(c.asset_classes),
            "real_time": c.real_time,
        }
        attribution, license_note = c.attribution, c.license_note
        health = provider.health()
    state = registry.get_state(db, name) if name != "null" else None
    return MarketProviderPublicOut(
        name=name,
        role=role,
        enabled=bool(state.enabled) if state else False,
        healthy=bool(state and state.enabled and state.circuit_state == "closed" and health.healthy),
        circuit_state=state.circuit_state if state else "closed",
        last_success_at=state.last_success_at if state else None,
        attribution=attribution or None,
        license_note=license_note or None,
        capabilities=caps,
    )


@router.get("/status", response_model=ProvidersOverviewOut)
def providers_status(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> ProvidersOverviewOut:
    market = [
        _market_entry(db, settings.market_equity_provider, "equity"),
        _market_entry(db, settings.market_crypto_provider, "crypto"),
        _market_entry(db, settings.market_fx_provider, "fx"),
    ]
    db.commit()
    news = [
        ProviderStatusOut.model_validate({**p.__dict__, "healthy": p.circuit_state == "closed"})
        for p in db.scalars(select(Provider).order_by(Provider.name)).all()
    ]
    return ProvidersOverviewOut(
        market=market,
        news=news,
        prediction_enabled=settings.prediction_enabled,
        quote_freshness_minutes=settings.quote_freshness_minutes,
    )
