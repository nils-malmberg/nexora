"""specs/API_SPEC.md: `GET /education/{slug}`. Public (no auth): static,
non-sensitive editorial content, identical for every user — the theory
behind every figure the dashboard shows (see app/education_content.py)."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from app.education_content import ARTICLES, CATEGORIES
from app.schemas.education import EducationArticleOut, EducationSectionOut, EducationSummaryOut

router = APIRouter(prefix="/api/v1/education", tags=["education"])


@router.get("", response_model=list[EducationSummaryOut])
def list_education(
    q: str | None = Query(default=None, max_length=80), category: str | None = None
) -> list[EducationSummaryOut]:
    out = []
    needle = q.lower() if q else None
    for slug, article in ARTICLES.items():
        if category and article["category"] != category:
            continue
        if needle:
            haystack = " ".join(
                [
                    article["title"],
                    article["summary"],
                    article["what_it_measures"],
                    article["method"],
                    article["limitations"],
                ]
                + [s["heading"] + " " + s["body"] for s in article["sections"]]
            ).lower()
            if needle not in haystack:
                continue
        out.append(
            EducationSummaryOut(
                slug=slug, title=article["title"], category=article["category"], summary=article["summary"]
            )
        )
    return out


@router.get("/categories", response_model=list[dict])
def list_categories() -> list[dict]:
    return [{"key": key, "label": label} for key, label in CATEGORIES.items()]


@router.get("/{slug}", response_model=EducationArticleOut)
def get_education(slug: str) -> EducationArticleOut:
    article = ARTICLES.get(slug)
    if article is None:
        raise HTTPException(status_code=404, detail="unknown education article")
    return EducationArticleOut(
        slug=slug,
        title=article["title"],
        category=article["category"],
        summary=article["summary"],
        what_it_measures=article["what_it_measures"],
        method=article["method"],
        limitations=article["limitations"],
        sections=[EducationSectionOut(**s) for s in article["sections"]],
        related=article.get("related", []),
        version=article["version"],
    )
