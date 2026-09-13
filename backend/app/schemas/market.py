from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field, field_validator

from app.models import ASSET_CLASSES
from app.schemas.instruments import InstrumentOut


class CandidateOut(BaseModel):
    symbol: str
    name: str
    asset_class: str
    currency: str | None
    exchange: str | None
    provider: str
    provider_symbol: str
    instrument_id: str | None
    in_catalog: bool


class SearchOut(BaseModel):
    query: str
    candidates: list[CandidateOut]
    providers_queried: list[str]
    provider_errors: dict[str, str]


class CatalogAddRequest(BaseModel):
    provider: str = Field(min_length=1, max_length=20)
    provider_symbol: str = Field(min_length=1, max_length=80)
    symbol: str = Field(min_length=1, max_length=32)
    name: str = Field(min_length=1, max_length=200)
    asset_class: str
    currency: str | None = Field(default=None, min_length=3, max_length=8)
    exchange: str | None = Field(default=None, max_length=40)
    isin: str | None = Field(default=None, max_length=20)

    @field_validator("asset_class")
    @classmethod
    def _valid_asset_class(cls, value: str) -> str:
        if value not in ASSET_CLASSES:
            raise ValueError(f"asset_class must be one of {ASSET_CLASSES}")
        return value

    @field_validator("currency")
    @classmethod
    def _upper(cls, value: str | None) -> str | None:
        return value.upper() if value else value


class CatalogAddOut(BaseModel):
    instrument: InstrumentOut
    created: bool
    warning: str | None


class QuoteOut(BaseModel):
    instrument_id: str
    price: Decimal | None
    currency: str | None
    as_of: datetime | None
    collected_at: datetime | None
    source: str | None
    is_delayed: bool
    is_estimate: bool
    status: str
    reason: str | None
    freshness: str
    age_seconds: float | None
    previous_close: Decimal | None
    change_pct: Decimal | None
    provider: str | None
    license_note: str | None
    attribution: str | None


class BarOut(BaseModel):
    as_of: datetime
    open: Decimal | None
    high: Decimal | None
    low: Decimal | None
    close: Decimal
    volume: Decimal | None


class HistoryOut(BaseModel):
    instrument_id: str
    interval: str
    currency: str | None
    start: datetime
    end: datetime
    bars: list[BarOut]
    has_ohlc: bool
    source: str | None
    status: str
    reason: str | None
    license_note: str | None
    attribution: str | None


class WatchlistItemOut(BaseModel):
    id: str
    instrument: InstrumentOut
    quote: QuoteOut | None
    held: bool = False
    entry_price: Decimal | None = None
    entry_date: datetime | None = None
    quantity: Decimal | None = None
    note: str | None = None
    created_at: datetime


class WatchlistAddRequest(BaseModel):
    instrument_id: str


class WatchlistUpdateRequest(BaseModel):
    """'Je détiens ce titre' with an optional entry price/date/quantity — a
    note to oneself the decision aid uses to frame 'sell or hold', never a
    transaction."""

    held: bool | None = None
    entry_price: Decimal | None = Field(default=None, gt=0)
    entry_date: datetime | None = None
    quantity: Decimal | None = Field(default=None, gt=0)
    note: str | None = Field(default=None, max_length=200)
    clear_entry: bool = False


class QuickBuyRequest(BaseModel):
    """'Ajouter au portefeuille' from the market page: one purchase at a
    price the user confirms (prefilled with the last quote — never executed
    anywhere, only recorded)."""

    portfolio_id: str
    quantity: Decimal = Field(gt=0)
    unit_price: Decimal = Field(gt=0)
    currency: str = Field(min_length=3, max_length=8)
    trade_date: datetime | None = None
    fees: Decimal = Field(default=Decimal("0"), ge=0)
    note: str | None = Field(default=None, max_length=500)
    # Records a matching `depot` just before the purchase, so tracking a
    # holding bought with money outside the app doesn't show as negative
    # cash. Off when the portfolio's cash is already tracked (deposits
    # entered explicitly).
    fund_with_deposit: bool = True

    @field_validator("currency")
    @classmethod
    def _upper(cls, value: str) -> str:
        return value.upper()


class MarketOverviewEntry(BaseModel):
    instrument: InstrumentOut
    quote: QuoteOut | None
    held_quantity: Decimal | None = None
    watched: bool = False
    held: bool = False  # portfolio position or watchlist "je détiens"
    entry_price: Decimal | None = None
    watchlist_item_id: str | None = None
