"""Central asset resolution.

Adapters never touch the database; they only propose an `asset_hint`
(either the id of a feed's bound asset, or a raw symbol/keyword found in the
content). This module is the single place that turns that hint into a real
`Asset` row, so every adapter is resolved the same way.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Asset


@dataclass
class AssetResolution:
    asset_id: str | None
    method: str  # explicit | keyword | unmatched
    confidence: float


def resolve_asset(db: Session, asset_hint: str | None, proposed_confidence: float) -> AssetResolution:
    if not asset_hint:
        return AssetResolution(None, "unmatched", 0.0)

    if db.get(Asset, asset_hint) is not None:
        return AssetResolution(asset_hint, "explicit", 1.0)

    asset = db.scalar(select(Asset).where(Asset.symbol.ilike(asset_hint)))
    if asset is not None:
        return AssetResolution(asset.id, "keyword", proposed_confidence)

    return AssetResolution(None, "unmatched", 0.0)
