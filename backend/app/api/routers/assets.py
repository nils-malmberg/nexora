from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.models import Asset
from app.schemas.assets import AssetOut

router = APIRouter(prefix="/api/v1/assets", tags=["assets"])


@router.get("", response_model=list[AssetOut])
def list_assets(q: str | None = None, db: Session = Depends(get_db)) -> list[Asset]:
    query = select(Asset).order_by(Asset.symbol)
    if q:
        query = query.where(Asset.symbol.ilike(f"%{q}%") | Asset.name.ilike(f"%{q}%"))
    return list(db.scalars(query.limit(50)).all())


@router.get("/{asset_id}", response_model=AssetOut)
def get_asset(asset_id: str, db: Session = Depends(get_db)) -> Asset:
    asset = db.get(Asset, asset_id)
    if asset is None:
        raise HTTPException(status_code=404, detail="asset not found")
    return asset
