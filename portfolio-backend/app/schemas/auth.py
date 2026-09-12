from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, EmailStr, Field, field_validator


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=10, max_length=200)
    display_name: str | None = Field(default=None, max_length=120)
    reference_currency: str = Field(default="EUR", min_length=3, max_length=8)

    @field_validator("reference_currency")
    @classmethod
    def _upper(cls, value: str) -> str:
        return value.upper()


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class UserOut(BaseModel):
    id: str
    email: str
    display_name: str | None
    reference_currency: str
    created_at: datetime

    model_config = {"from_attributes": True}


class AuthResponse(BaseModel):
    """`csrf_token` is returned once, in the body — the session cookie itself
    is HttpOnly (unreadable from JS), so the frontend must be handed the CSRF
    token this other way and echo it back as a header on mutating requests."""

    user: UserOut
    csrf_token: str
