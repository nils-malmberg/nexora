from __future__ import annotations

import uuid

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from sqlalchemy import text

from app.api.deps import get_db
from app.api.errors import register_error_handlers
from app.api.routers import (
    admin,
    analytics,
    auth,
    education,
    events,
    imports,
    instruments,
    market,
    me,
    news,
    portfolios,
    prediction,
    providers,
    timeline,
)
from app.config import settings
from app.observability.logging import configure_logging

configure_logging(settings.log_level)

app = FastAPI(
    title="NeXora API",
    version="1.0.0",
    description=(
        "Dashboard multi-actifs : marchés, portefeuille, analyse, actualités, aide, prédiction expérimentale. "
        "Consultation et analyse uniquement — aucun ordre, aucune recommandation."
    ),
    docs_url="/docs" if settings.environment != "production" else None,
    redoc_url=None,
)
register_error_handlers(app)

# Same-origin by default (nginx serves the SPA and proxies /api). A separate
# dev origin (vite on :5173) is allowed only when listed explicitly — the
# cookie-based auth forbids a "*" allowlist with credentials.
_origins = [o.strip() for o in settings.cors_allowed_origins.split(",") if o.strip()]
if _origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "DELETE"],
        allow_headers=["Content-Type", "X-CSRF-Token"],
    )

_CSP = (
    "default-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'; "
    "img-src 'self' data:; style-src 'self' 'unsafe-inline'; script-src 'self'; connect-src 'self'"
)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    """Request correlation id + defensive headers (specs/SECURITY.md: CSP,
    no framing, no MIME sniffing). The API serves JSON only, so a strict CSP
    costs nothing here; the SPA's own CSP is set by nginx (frontend/nginx.conf)."""
    request.state.request_id = request.headers.get("x-request-id", uuid.uuid4().hex)
    response = await call_next(request)
    response.headers["X-Request-ID"] = request.state.request_id
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Cache-Control"] = "no-store"
    response.headers["Permissions-Policy"] = "geolocation=(), camera=(), microphone=()"
    if not request.url.path.startswith("/docs") and not request.url.path.startswith("/openapi"):
        response.headers["Content-Security-Policy"] = _CSP
    return response


for router in (
    auth.router,
    me.router,
    portfolios.router,
    instruments.router,
    market.router,
    imports.router,
    analytics.router,
    news.router,
    timeline.router,
    events.router,
    education.router,
    prediction.router,
    providers.router,
    admin.router,
):
    app.include_router(router)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/ready")
def ready() -> dict:
    db = next(get_db())
    try:
        db.execute(text("SELECT 1"))
    finally:
        db.close()
    return {"status": "ready"}


@app.get("/metrics")
def metrics() -> Response:
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)
