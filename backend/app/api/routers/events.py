from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.api.serializers import event_to_out
from app.models import Event
from app.schemas.events import EventOut

router = APIRouter(prefix="/api/v1/events", tags=["events"])

ALLOWED_STATUSES = {"confirme", "previsionnel", "reporte", "annule", "unknown"}


@router.get("/upcoming", response_model=list[EventOut])
def list_upcoming_events(
    asset_id: str | None = Query(default=None),
    status: str | None = Query(default=None),
    since: datetime | None = Query(default=None),
    until: datetime | None = Query(default=None),
    tz: str | None = Query(default=None, description="IANA timezone for displaying starts_at"),
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
) -> list[EventOut]:
    if status is not None and status not in ALLOWED_STATUSES:
        raise HTTPException(status_code=400, detail=f"unknown status '{status}'")

    display_tz = None
    if tz:
        try:
            display_tz = ZoneInfo(tz)
        except ZoneInfoNotFoundError as exc:
            raise HTTPException(status_code=400, detail=f"unknown timezone '{tz}'") from exc

    query = select(Event).order_by(Event.starts_at.asc().nulls_last())
    if asset_id:
        query = query.where(Event.asset_id == asset_id)
    if status:
        query = query.where(Event.status == status)
    else:
        query = query.where(Event.status != "annule")
    if since:
        query = query.where((Event.starts_at >= since) | (Event.starts_at.is_(None)))
    if until:
        query = query.where((Event.starts_at <= until) | (Event.starts_at.is_(None)))

    rows = list(db.scalars(query.limit(limit)).all())
    return [event_to_out(event, display_tz=display_tz) for event in rows]
