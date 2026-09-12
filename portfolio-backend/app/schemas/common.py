from __future__ import annotations

from typing import Generic, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


class Page(BaseModel, Generic[T]):
    items: list[T]
    next_cursor: str | None = None


class ErrorResponse(BaseModel):
    code: str
    message: str
    details: dict | None = None
    request_id: str
