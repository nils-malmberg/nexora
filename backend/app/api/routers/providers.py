from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_db, require_admin
from app.models import Provider
from app.pipeline.ingest import run_provider
from app.schemas.providers import IngestionRunOut, ProviderStatusOut

router = APIRouter(prefix="/api/v1", tags=["providers"])


def _to_status_out(provider: Provider) -> ProviderStatusOut:
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


@router.get("/providers/status", response_model=list[ProviderStatusOut])
def get_providers_status(db: Session = Depends(get_db)) -> list[ProviderStatusOut]:
    providers = db.scalars(select(Provider).order_by(Provider.name)).all()
    return [_to_status_out(p) for p in providers]


@router.post(
    "/admin/providers/{provider_id}/sync",
    response_model=IngestionRunOut,
    dependencies=[Depends(require_admin)],
)
def trigger_provider_sync(provider_id: str, db: Session = Depends(get_db)) -> IngestionRunOut:
    provider = db.get(Provider, provider_id)
    if provider is None:
        raise HTTPException(status_code=404, detail="provider not found")
    run = run_provider(db, provider)
    return IngestionRunOut.model_validate(run)
