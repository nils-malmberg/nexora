from __future__ import annotations

from collections.abc import Generator
from datetime import UTC, datetime

from fastapi import Depends, Header, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.db import SessionLocal
from app.models import Portfolio, User, UserSession
from app.security import constant_time_equals, hash_token


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_current_session(request: Request, db: Session = Depends(get_db)) -> UserSession:
    token = request.cookies.get(settings.session_cookie_name)
    if not token:
        raise HTTPException(status_code=401, detail="not authenticated")
    token_hash = hash_token(token)
    session = db.scalars(select(UserSession).where(UserSession.token_hash == token_hash)).first()
    now = datetime.now(UTC)
    if session is None or session.revoked_at is not None or session.expires_at < now:
        raise HTTPException(status_code=401, detail="session expired or invalid")
    session.last_seen_at = now
    db.commit()
    return session


def get_current_user(session: UserSession = Depends(get_current_session), db: Session = Depends(get_db)) -> User:
    user = db.get(User, session.user_id)
    if user is None or not user.is_active:
        raise HTTPException(status_code=401, detail="not authenticated")
    return user


def require_csrf(
    request: Request,
    session: UserSession = Depends(get_current_session),
    x_csrf_token: str | None = Header(default=None),
) -> None:
    """CSRF check for mutating requests: the cookie alone authenticates the
    browser, but a cross-site form/fetch can ride along with it — the
    frontend must additionally echo the token it was handed once at
    login/register (see AuthResponse), which a third-party page cannot read
    (it isn't in the cookie, and CORS blocks a cross-origin JS read of the
    response body) — specs/SECURITY.md: "CSRF"."""
    if request.method in ("GET", "HEAD", "OPTIONS"):
        return
    if not x_csrf_token or not constant_time_equals(x_csrf_token, session.csrf_token):
        raise HTTPException(status_code=403, detail="missing or invalid CSRF token")


def get_owned_portfolio(portfolio_id: str, db: Session, user: User) -> Portfolio:
    """Tenant-aware lookup: a portfolio that exists but belongs to another
    user is reported as 404, never 403 — specs/SECURITY.md IDOR control (403
    would confirm the id exists to an attacker probing other users' ids)."""
    portfolio = db.get(Portfolio, portfolio_id)
    if portfolio is None or portfolio.user_id != user.id:
        raise HTTPException(status_code=404, detail="portfolio not found")
    return portfolio
