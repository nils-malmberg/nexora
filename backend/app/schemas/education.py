from __future__ import annotations

from pydantic import BaseModel


class EducationSectionOut(BaseModel):
    heading: str
    body: str


class EducationSummaryOut(BaseModel):
    slug: str
    title: str
    category: str
    summary: str


class EducationArticleOut(BaseModel):
    slug: str
    title: str
    category: str
    summary: str
    what_it_measures: str
    method: str
    limitations: str
    sections: list[EducationSectionOut]
    related: list[str]
    version: str
