from __future__ import annotations

from pydantic import BaseModel


class AssetOut(BaseModel):
    id: str
    symbol: str
    name: str
    isin: str | None
    market: str | None
    currency: str | None

    model_config = {"from_attributes": True}
