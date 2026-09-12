from __future__ import annotations

import uuid

from fastapi import FastAPI, Request
from fastapi.responses import Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from sqlalchemy import text

from app.api.deps import get_db
from app.api.errors import register_error_handlers
from app.api.routers import assets, events, news, providers, timeline
from app.config import settings
from app.observability.logging import configure_logging

configure_logging(settings.log_level)

app = FastAPI(title="NeXora News & Events API", version="0.1.0")
register_error_handlers(app)


@app.middleware("http")
async def add_request_id(request: Request, call_next):
    request.state.request_id = request.headers.get("x-request-id", uuid.uuid4().hex)
    response = await call_next(request)
    response.headers["X-Request-ID"] = request.state.request_id
    return response


app.include_router(assets.router)
app.include_router(news.router)
app.include_router(timeline.router)
app.include_router(events.router)
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
