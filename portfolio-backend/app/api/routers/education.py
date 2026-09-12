"""specs/API_SPEC.md: `GET /education/{slug}`. Public (no auth) - static,
non-sensitive editorial content, same for every user - see
app/education_content.py."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.education_content import ARTICLES
from app.schemas.education import EducationArticleOut, EducationSummaryOut

router = APIRouter(prefix="/api/v1/education", tags=["education"])


@router.get("", response_model=list[EducationSummaryOut])
def list_education() -> list[EducationSummaryOut]:
    return [EducationSummaryOut(slug=slug, title=article["title"]) for slug, article in ARTICLES.items()]


@router.get("/{slug}", response_model=EducationArticleOut)
def get_education(slug: str) -> EducationArticleOut:
    article = ARTICLES.get(slug)
    if article is None:
        raise HTTPException(status_code=404, detail="unknown education article")
    return EducationArticleOut(slug=slug, **article)
