"""Transaction request/response schemas.

`transfert` and `valorisation_privee` are valid persisted transaction types
(see app.models.TRANSACTION_TYPES, kept forward-compatible with the CSV
import format in specs/PORTFOLIO_IMPORTS.md) but are not yet creatable
through this API — see SUPPORTED_API_TYPES below and portfolio-backend/README.md
"Limites connues". A private valuation is instead recorded through the
dedicated `POST /instruments/{id}/private-valuations` endpoint.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field, model_validator

from app.models import CASH_ONLY_TRANSACTION_TYPES

SUPPORTED_API_TYPES = ("achat", "vente", "dividende", "coupon", "depot", "retrait", "split")
INSTRUMENT_REQUIRED_TYPES = ("achat", "vente", "dividende", "coupon", "split")
CASH_ONLY_NO_INSTRUMENT_TYPES = ("depot", "retrait")


class TransactionCreate(BaseModel):
    instrument_id: str | None = None
    type: str
    trade_date: datetime
    quantity: Decimal = Field(gt=0)
    unit_price: Decimal = Field(gt=0)
    currency: str = Field(min_length=3, max_length=8)
    fees: Decimal = Field(default=Decimal("0"), ge=0)
    account: str | None = Field(default=None, max_length=80)
    external_id: str | None = Field(default=None, max_length=200)
    note: str | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def _validate_type_shape(self) -> TransactionCreate:
        if self.type not in SUPPORTED_API_TYPES:
            raise ValueError(
                f"type '{self.type}' is not yet supported via this API "
                f"(supported: {SUPPORTED_API_TYPES}); private valuations use "
                "POST /instruments/{id}/private-valuations instead"
            )
        if self.type in INSTRUMENT_REQUIRED_TYPES and not self.instrument_id:
            raise ValueError(f"instrument_id is required for type '{self.type}'")
        if self.type in CASH_ONLY_NO_INSTRUMENT_TYPES and self.instrument_id:
            raise ValueError(f"instrument_id must not be set for type '{self.type}' (cash-only movement)")
        if self.type in CASH_ONLY_TRANSACTION_TYPES and self.quantity != 1:
            raise ValueError(f"quantity must be exactly 1 for type '{self.type}' — unit_price carries the cash amount")
        self.currency = self.currency.upper()
        return self


class TransactionReverseRequest(BaseModel):
    reason: str = Field(min_length=1, max_length=500)


class TransactionOut(BaseModel):
    id: str
    portfolio_id: str
    instrument_id: str | None
    type: str
    trade_date: datetime
    quantity: Decimal
    unit_price: Decimal
    currency: str
    fees: Decimal
    account: str | None
    external_id: str | None
    note: str | None
    reversed_at: datetime | None
    reversal_reason: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class PositionOut(BaseModel):
    instrument_id: str
    symbol: str
    name: str
    quantity: Decimal
    average_unit_cost: Decimal
    currency: str
    price: Decimal | None
    price_as_of: datetime | None
    market_value: Decimal | None
    freshness: str
    matches_base_currency: bool


class ValuationOut(BaseModel):
    base_currency: str
    cash: Decimal
    cash_by_currency: dict[str, Decimal]
    positions_value: Decimal
    total_value: Decimal
    unconverted_currencies: list[str]
    has_missing_prices: bool
    positions: list[PositionOut]
