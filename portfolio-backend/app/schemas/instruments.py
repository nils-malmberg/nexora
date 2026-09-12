from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field, field_validator

from app.models import ASSET_CLASSES


class InstrumentCreate(BaseModel):
    symbol: str = Field(min_length=1, max_length=32)
    name: str = Field(min_length=1, max_length=200)
    asset_class: str
    isin: str | None = Field(default=None, max_length=20)
    currency: str = Field(min_length=3, max_length=8)

    @field_validator("asset_class")
    @classmethod
    def _valid_asset_class(cls, value: str) -> str:
        if value not in ASSET_CLASSES:
            raise ValueError(f"asset_class must be one of {ASSET_CLASSES}")
        return value

    @field_validator("currency", "symbol")
    @classmethod
    def _upper(cls, value: str) -> str:
        return value.upper()


class InstrumentOut(BaseModel):
    id: str
    symbol: str
    name: str
    asset_class: str
    isin: str | None
    currency: str
    created_at: datetime

    model_config = {"from_attributes": True}


class PricePointCreate(BaseModel):
    as_of: datetime
    price: Decimal = Field(gt=0)
    currency: str = Field(min_length=3, max_length=8)
    is_estimate: bool = False

    @field_validator("currency")
    @classmethod
    def _upper(cls, value: str) -> str:
        return value.upper()


class PricePointOut(BaseModel):
    id: str
    instrument_id: str
    as_of: datetime
    price: Decimal
    currency: str
    source: str
    is_estimate: bool
    collected_at: datetime

    model_config = {"from_attributes": True}


class PrivateValuationCreate(BaseModel):
    valuation_date: datetime
    valuation_amount: Decimal = Field(gt=0)
    currency: str = Field(min_length=3, max_length=8)
    method: str = Field(min_length=1, max_length=200)
    confidence: Decimal = Field(default=Decimal("0.5"), ge=0, le=1)
    note: str | None = Field(default=None, max_length=500)

    @field_validator("currency")
    @classmethod
    def _upper(cls, value: str) -> str:
        return value.upper()


class PrivateValuationOut(BaseModel):
    id: str
    instrument_id: str
    valuation_date: datetime
    valuation_amount: Decimal
    currency: str
    method: str
    confidence: Decimal
    note: str | None
    created_at: datetime

    model_config = {"from_attributes": True}
