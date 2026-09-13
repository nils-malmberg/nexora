"""Transaction request/response schemas.

`transfert` is a valid persisted transaction type (see
app.models.TRANSACTION_TYPES, kept forward-compatible with the CSV import
format in specs/PORTFOLIO_IMPORTS.md) but is not yet creatable through this
API — its semantics need a source AND destination account, which the current
schema's single `account` field cannot express. See SUPPORTED_API_TYPES below
and portfolio-backend/README.md "Limites connues".

`valorisation_privee` IS supported here (and via CSV import): it creates the
Transaction row for audit/history (no cash or lot effect — see
app.domain.positions.cash_delta/replay_lots) plus a linked PrivateValuation
and PricePoint, exactly as `POST /instruments/{id}/private-valuations` does —
see app.domain.positions.apply_transaction.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field, model_validator

from app.models import CASH_ONLY_TRANSACTION_TYPES

SUPPORTED_API_TYPES = ("achat", "vente", "dividende", "coupon", "depot", "retrait", "split", "valorisation_privee")
INSTRUMENT_REQUIRED_TYPES = ("achat", "vente", "dividende", "coupon", "split", "valorisation_privee")
CASH_ONLY_NO_INSTRUMENT_TYPES = ("depot", "retrait")
SINGLE_QUANTITY_TYPES = (*CASH_ONLY_TRANSACTION_TYPES, "valorisation_privee")


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
    # Only meaningful (and required) for type="valorisation_privee" — mirrors
    # PrivateValuationCreate's own fields (app.schemas.instruments).
    method: str | None = Field(default=None, max_length=200)
    confidence: Decimal | None = Field(default=None, ge=0, le=1)

    @model_validator(mode="after")
    def _validate_type_shape(self) -> TransactionCreate:
        if self.type not in SUPPORTED_API_TYPES:
            raise ValueError(f"type '{self.type}' is not yet supported via this API (supported: {SUPPORTED_API_TYPES})")
        if self.type in INSTRUMENT_REQUIRED_TYPES and not self.instrument_id:
            raise ValueError(f"instrument_id is required for type '{self.type}'")
        if self.type in CASH_ONLY_NO_INSTRUMENT_TYPES and self.instrument_id:
            raise ValueError(f"instrument_id must not be set for type '{self.type}' (cash-only movement)")
        if self.type in SINGLE_QUANTITY_TYPES and self.quantity != 1:
            raise ValueError(f"quantity must be exactly 1 for type '{self.type}' — unit_price carries the amount")
        if self.type == "valorisation_privee" and not self.method:
            raise ValueError("method is required for type 'valorisation_privee'")
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
    asset_class: str
    quantity: Decimal
    average_unit_cost: Decimal
    cost_currency: str
    cost_basis: Decimal
    currency: str
    price: Decimal | None
    price_as_of: datetime | None
    price_source: str | None
    market_value: Decimal | None
    market_value_base: Decimal | None
    unrealized_pnl: Decimal | None
    freshness: str
    matches_base_currency: bool
    fx_rate: Decimal | None = None
    fx_rate_as_of: datetime | None = None
    fx_source: str | None = None


class FxNoteOut(BaseModel):
    currency: str
    rate: Decimal
    rate_as_of: datetime
    source: str


class ValuationOut(BaseModel):
    base_currency: str
    cash: Decimal
    cash_by_currency: dict[str, Decimal]
    positions_value: Decimal
    total_value: Decimal
    unconverted_currencies: list[str]
    has_missing_prices: bool
    fx_rates: list[FxNoteOut]
    as_of: datetime
    positions: list[PositionOut]
