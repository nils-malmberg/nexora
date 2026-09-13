"""Administration (admin role only): news providers and their ingestion,
market providers' enable/disable, and the prediction kill switch state.
Every action is audited."""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_db, require_admin, require_csrf
from app.config import settings
from app.market import registry
from app.models import AuditEvent, IngestionRun, MarketProvider, Provider, User
from app.news.pipeline.ingest import run_provider
from app.schemas.providers import IngestionRunOut, MarketProviderStateOut, ProviderStatusOut

router = APIRouter(prefix="/api/v1/admin", tags=["admin"])


class EnableRequest(BaseModel):
    enabled: bool
    reason: str | None = None


def _news_status(provider: Provider) -> ProviderStatusOut:
    return ProviderStatusOut(
        id=provider.id,
        name=provider.name,
        type=provider.type,
        enabled=provider.enabled,
        circuit_state=provider.circuit_state,
        consecutive_failures=provider.consecutive_failures,
        last_attempt_at=provider.last_attempt_at,
        last_success_at=provider.last_success_at,
        healthy=provider.circuit_state == "closed",
        license_note=provider.license_note,
    )


@router.get("/news-providers", response_model=list[ProviderStatusOut])
def list_news_providers(admin: User = Depends(require_admin), db: Session = Depends(get_db)) -> list[ProviderStatusOut]:
    return [_news_status(p) for p in db.scalars(select(Provider).order_by(Provider.name)).all()]


@router.post("/news-providers/{provider_id}/sync", response_model=IngestionRunOut)
def trigger_provider_sync(
    provider_id: str,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
    _csrf: None = Depends(require_csrf),
) -> IngestionRunOut:
    provider = db.get(Provider, provider_id)
    if provider is None:
        raise HTTPException(status_code=404, detail="provider not found")
    db.add(AuditEvent(user_id=admin.id, action="provider.sync", target_type="provider", target_id=provider.id))
    run = run_provider(db, provider)
    return IngestionRunOut.model_validate(run)


@router.post("/news-providers/{provider_id}/enabled", response_model=ProviderStatusOut)
def set_news_provider_enabled(
    provider_id: str,
    payload: EnableRequest,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
    _csrf: None = Depends(require_csrf),
) -> ProviderStatusOut:
    provider = db.get(Provider, provider_id)
    if provider is None:
        raise HTTPException(status_code=404, detail="provider not found")
    provider.enabled = payload.enabled
    if payload.enabled:
        provider.consecutive_failures = 0
        provider.circuit_state = "closed"
    db.add(
        AuditEvent(
            user_id=admin.id,
            action="provider.enable" if payload.enabled else "provider.disable",
            target_type="provider",
            target_id=provider.id,
            event_metadata={"reason": payload.reason},
        )
    )
    db.commit()
    return _news_status(provider)


@router.get("/news-providers/{provider_id}/runs", response_model=list[IngestionRunOut])
def list_runs(
    provider_id: str, admin: User = Depends(require_admin), db: Session = Depends(get_db)
) -> list[IngestionRunOut]:
    runs = db.scalars(
        select(IngestionRun)
        .where(IngestionRun.provider_id == provider_id)
        .order_by(IngestionRun.started_at.desc())
        .limit(50)
    ).all()
    return [IngestionRunOut.model_validate(r) for r in runs]


@router.get("/market-providers", response_model=list[MarketProviderStateOut])
def list_market_providers(
    admin: User = Depends(require_admin), db: Session = Depends(get_db)
) -> list[MarketProviderStateOut]:
    names = [*registry.configured_provider_names(), settings.market_fx_provider]
    out = []
    for name in names:
        if name == "null":
            continue
        state = registry.get_state(db, name)
        out.append(MarketProviderStateOut.model_validate(state))
    db.commit()
    return out


@router.post("/market-providers/{name}/enabled", response_model=MarketProviderStateOut)
def set_market_provider_enabled(
    name: str,
    payload: EnableRequest,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
    _csrf: None = Depends(require_csrf),
) -> MarketProviderStateOut:
    state = db.get(MarketProvider, name)
    if state is None:
        raise HTTPException(status_code=404, detail="market provider not found")
    state.enabled = payload.enabled
    state.disabled_reason = None if payload.enabled else (payload.reason or "disabled by admin")
    if payload.enabled:
        state.consecutive_failures = 0
        state.circuit_state = "closed"
        state.last_error = None
    state.updated_at = datetime.now(UTC)
    db.add(
        AuditEvent(
            user_id=admin.id,
            action="market_provider.enable" if payload.enabled else "market_provider.disable",
            target_type="market_provider",
            target_id=name,
            event_metadata={"reason": payload.reason},
        )
    )
    db.commit()
    return MarketProviderStateOut.model_validate(state)


@router.get("/audit", response_model=list[dict])
def recent_audit(admin: User = Depends(require_admin), db: Session = Depends(get_db)) -> list[dict]:
    rows = db.scalars(select(AuditEvent).order_by(AuditEvent.created_at.desc()).limit(100)).all()
    return [
        {
            "id": r.id,
            "action": r.action,
            "target_type": r.target_type,
            "target_id": r.target_id,
            "user_id": r.user_id,
            "created_at": r.created_at.isoformat(),
            "metadata": r.event_metadata,
        }
        for r in rows
    ]
