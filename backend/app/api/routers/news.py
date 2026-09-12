from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from sqlalchemy import or_, select, tuple_
from sqlalchemy.orm import Session

from app.adapters.common import ALLOWED_CATEGORIES, ALLOWED_KINDS
from app.api.deps import get_db
from app.api.pagination import clamp_page_size, decode_cursor, encode_cursor
from app.api.serializers import compute_list_etag, news_item_to_out
from app.config import settings
from app.models import Asset, NewsItem, NewsItemAsset
from app.observability.metrics import stale_responses_total
from app.schemas.common import Page
from app.schemas.news import NewsItemOut

router = APIRouter(prefix="/api/v1/assets", tags=["news"])


@router.get("/{asset_id}/news", response_model=Page[NewsItemOut])
def list_asset_news(
    asset_id: str,
    request: Request,
    response: Response,
    category: str | None = Query(default=None),
    kind: str | None = Query(default=None),
    since: datetime | None = Query(default=None),
    until: datetime | None = Query(default=None),
    q: str | None = Query(
        default=None, min_length=1, max_length=200, description="Recherche texte (titre/résumé/extrait)"
    ),
    cursor: str | None = Query(default=None),
    limit: int | None = Query(default=None, ge=1),
    db: Session = Depends(get_db),
) -> Page[NewsItemOut]:
    if db.get(Asset, asset_id) is None:
        raise HTTPException(status_code=404, detail="asset not found")
    if category is not None and category not in ALLOWED_CATEGORIES:
        raise HTTPException(status_code=400, detail=f"unknown category '{category}'")
    if kind is not None and kind not in ALLOWED_KINDS:
        raise HTTPException(status_code=400, detail=f"unknown kind '{kind}'")

    page_size = clamp_page_size(limit, settings.default_page_size, settings.max_page_size)

    query = (
        select(NewsItem)
        .join(NewsItemAsset, NewsItemAsset.news_item_id == NewsItem.id)
        .where(NewsItemAsset.asset_id == asset_id)
        .order_by(NewsItem.publication_at.desc(), NewsItem.id.desc())
    )
    if category:
        query = query.where(NewsItem.category == category)
    if kind:
        query = query.where(NewsItem.kind == kind)
    if since:
        query = query.where(NewsItem.publication_at >= since)
    if until:
        query = query.where(NewsItem.publication_at <= until)
    if q:
        pattern = f"%{q}%"
        query = query.where(
            or_(NewsItem.title.ilike(pattern), NewsItem.excerpt.ilike(pattern), NewsItem.summary.ilike(pattern))
        )
    if cursor:
        cursor_key, cursor_id = decode_cursor(cursor)
        query = query.where(tuple_(NewsItem.publication_at, NewsItem.id) < tuple_(cursor_key, cursor_id))

    rows = list(db.scalars(query.limit(page_size + 1)).all())
    has_more = len(rows) > page_size
    rows = rows[:page_size]

    etag = compute_list_etag([(row.id, row.updated_at) for row in rows])
    if request.headers.get("if-none-match") == etag:
        response.status_code = 304
        return Page(items=[], next_cursor=None)

    out_items = [news_item_to_out(row, db) for row in rows]
    if any(item.stale for item in out_items):
        stale_responses_total.labels(endpoint="assets_news").inc()

    next_cursor = encode_cursor(rows[-1].publication_at, rows[-1].id) if has_more and rows else None
    response.headers["ETag"] = etag
    return Page(items=out_items, next_cursor=next_cursor)
