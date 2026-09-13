from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class RowResultOut(BaseModel):
    row_number: int
    status: str  # valid | duplicate | error | inserted
    messages: list[str]
    canonical: dict[str, str | None] | None


class ImportJobSummaryOut(BaseModel):
    id: str
    filename: str
    status: str
    total_rows: int
    valid_count: int
    duplicate_count: int
    error_count: int
    inserted_count: int
    created_at: datetime
    previewed_at: datetime | None
    committed_at: datetime | None


class ImportJobOut(ImportJobSummaryOut):
    preset: str | None = None
    preset_label: str | None = None
    delimiter: str
    encoding: str
    column_mapping: dict[str, str]
    suggested_mapping: dict[str, str] | None = None
    headers: list[str] | None = None
    sample_rows: list[dict[str, str]] | None = None
    rows: list[RowResultOut] | None = None
    resolved_isins: dict[str, str] | None = None


class ImportPreviewRequest(BaseModel):
    column_mapping: dict[str, str] = Field(default_factory=dict)
    default_timezone: str = "UTC"
    # None = keep the detected preset; "" = force the generic mapping; a key = force that preset.
    preset: str | None = None


class PresetOut(BaseModel):
    key: str
    label: str
    instructions: list[str]
    notes: list[str]
