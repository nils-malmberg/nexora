from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.adapters.market_data import get_active_provider
from app.api.deps import get_current_user
from app.models import User

router = APIRouter(prefix="/api/v1/providers", tags=["providers"])


class ProviderStatusOut(BaseModel):
    name: str
    healthy: bool
    detail: str


@router.get("/status", response_model=ProviderStatusOut)
def provider_status(user: User = Depends(get_current_user)) -> ProviderStatusOut:
    """Always reports the safe null default in this PR — see
    app/adapters/market_data.py for why no real provider is wired in yet."""
    provider = get_active_provider()
    health = provider.health()
    return ProviderStatusOut(name=provider.name, healthy=health.healthy, detail=health.detail)
