from __future__ import annotations

from pydantic import BaseModel


class EducationSummaryOut(BaseModel):
    slug: str
    title: str


class EducationArticleOut(BaseModel):
    slug: str
    title: str
    what_it_measures: str
    method: str
    limitations: str
    version: str
