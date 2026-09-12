from __future__ import annotations

import uuid

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from sqlalchemy import text

from app.api.deps import get_db
from app.api.errors import register_error_handlers
from app.api.routers import auth, instruments, me, portfolios, providers
from app.config import settings
from app.observability.logging import configure_logging

configure_logging(settings.log_level)

app = FastAPI(title="NeXora Portfolio API", version="0.1.0")
register_error_handlers(app)

# Unlike the News & Events module's cookie-less, "*"-origin API, this API
# authenticates via a cookie: allow_credentials=True requires an explicit
# origin allowlist (the CORS spec forbids combining it with "*") — see
# specs/SECURITY.md.
_origins = [o.strip() for o in settings.cors_allowed_origins.split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE"],
    allow_headers=["Content-Type", "X-CSRF-Token"],
)


@app.middleware("http")
async def add_request_id(request: Request, call_next):
    request.state.request_id = request.headers.get("x-request-id", uuid.uuid4().hex)
    response = await call_next(request)
    response.headers["X-Request-ID"] = request.state.request_id
    return response


app.include_router(auth.router)
app.include_router(portfolios.router)
app.include_router(instruments.router)
app.include_router(me.router)
app.include_router(providers.router)


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
