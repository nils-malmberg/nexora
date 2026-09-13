from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field, field_validator


class PortfolioCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    base_currency: str = Field(default="EUR", min_length=3, max_length=8)

    @field_validator("base_currency")
    @classmethod
    def _upper(cls, value: str) -> str:
        return value.upper()


class PortfolioUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)


class PortfolioOut(BaseModel):
    id: str
    name: str
    base_currency: str
    target_allocation: dict[str, float] | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
