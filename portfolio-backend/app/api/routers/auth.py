from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_session, get_current_user, get_db, require_csrf
from app.config import settings
from app.models import User, UserSession
from app.observability.metrics import auth_attempts_total
from app.schemas.auth import AuthResponse, LoginRequest, RegisterRequest, UserOut
from app.security import RateLimiter, generate_token, hash_password, hash_token, verify_password

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])

# Separate limiters: a login flood targets one victim account (keyed by
# email), a registration flood targets the service itself (keyed by client
# IP) - see specs/SECURITY.md "rate limiting".
_login_limiter = RateLimiter(settings.auth_rate_limit_attempts, settings.auth_rate_limit_window_seconds)
_register_limiter = RateLimiter(settings.auth_rate_limit_attempts, settings.auth_rate_limit_window_seconds)


def _issue_session(db: Session, response: Response, user: User, user_agent: str | None) -> str:
    token = generate_token()
    csrf_token = generate_token()
    now = datetime.now(UTC)
    session = UserSession(
        user_id=user.id,
        token_hash=hash_token(token),
        csrf_token=csrf_token,
        expires_at=now + timedelta(hours=settings.session_ttl_hours),
        user_agent=(user_agent or "")[:300] or None,
    )
    db.add(session)
    db.commit()
    response.set_cookie(
        key=settings.session_cookie_name,
        value=token,
        httponly=True,
        secure=settings.session_cookie_secure,
        samesite="lax",
        max_age=settings.session_ttl_hours * 3600,
        path="/",
    )
    return csrf_token


@router.post("/register", response_model=AuthResponse, status_code=201)
def register(
    payload: RegisterRequest, request: Request, response: Response, db: Session = Depends(get_db)
) -> AuthResponse:
    client_host = request.client.host if request.client else "unknown"
    if not _register_limiter.allow(f"register:{client_host}"):
        auth_attempts_total.labels(kind="register", outcome="rate_limited").inc()
        raise HTTPException(status_code=429, detail="too many registration attempts, try again later")
    _register_limiter.record(f"register:{client_host}")

    email = payload.email.lower()
    existing = db.scalars(select(User).where(User.email == email)).first()
    if existing is not None:
        auth_attempts_total.labels(kind="register", outcome="conflict").inc()
        raise HTTPException(status_code=409, detail="an account with this email already exists")

    user = User(
        email=email,
        password_hash=hash_password(payload.password),
        display_name=payload.display_name,
        reference_currency=payload.reference_currency,
    )
    db.add(user)
    db.commit()
    auth_attempts_total.labels(kind="register", outcome="success").inc()
    csrf_token = _issue_session(db, response, user, request.headers.get("user-agent"))
    return AuthResponse(user=UserOut.model_validate(user), csrf_token=csrf_token)


@router.post("/login", response_model=AuthResponse)
def login(payload: LoginRequest, request: Request, response: Response, db: Session = Depends(get_db)) -> AuthResponse:
    limiter_key = f"login:{payload.email.lower()}"
    if not _login_limiter.allow(limiter_key):
        auth_attempts_total.labels(kind="login", outcome="rate_limited").inc()
        raise HTTPException(status_code=429, detail="too many login attempts, try again later")
    _login_limiter.record(limiter_key)

    user = db.scalars(select(User).where(User.email == payload.email.lower())).first()
    if user is None or not user.is_active or not verify_password(user.password_hash, payload.password):
        auth_attempts_total.labels(kind="login", outcome="invalid_credentials").inc()
        raise HTTPException(status_code=401, detail="invalid email or password")

    auth_attempts_total.labels(kind="login", outcome="success").inc()
    csrf_token = _issue_session(db, response, user, request.headers.get("user-agent"))
    return AuthResponse(user=UserOut.model_validate(user), csrf_token=csrf_token)


@router.post("/logout", status_code=204)
def logout(
    response: Response,
    session: UserSession = Depends(get_current_session),
    db: Session = Depends(get_db),
    _csrf: None = Depends(require_csrf),
) -> None:
    session.revoked_at = datetime.now(UTC)
    db.commit()
    response.delete_cookie(settings.session_cookie_name, path="/")


@router.get("/me", response_model=AuthResponse)
def me(user: User = Depends(get_current_user), session: UserSession = Depends(get_current_session)) -> AuthResponse:
    """Same shape as register/login: a page reload only has the session
    cookie to go on (the CSRF token lives in frontend memory, not the
    cookie), so it must be handed back here too or every mutating request
    would 403 until the next login."""
    return AuthResponse(user=UserOut.model_validate(user), csrf_token=session.csrf_token)
