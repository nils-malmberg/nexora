from __future__ import annotations

import hmac
from collections.abc import Generator

from fastapi import Header, HTTPException
from sqlalchemy.orm import Session

from app.config import settings
from app.db import SessionLocal


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def require_admin(x_admin_key: str | None = Header(default=None)) -> None:
    """Placeholder access control for the admin/sync endpoints until this
    module is wired into the dashboard's real auth (OIDC/session) - see
    specs/SECURITY.md. An unset admin key disables the endpoints entirely
    rather than falling back to "no auth"."""
    if not settings.admin_api_key:
        raise HTTPException(status_code=503, detail="admin endpoints are not configured")
    if not x_admin_key or not hmac.compare_digest(x_admin_key, settings.admin_api_key):
        raise HTTPException(status_code=401, detail="invalid admin key")
