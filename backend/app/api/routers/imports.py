"""CSV import endpoints — specs/PORTFOLIO_IMPORTS.md.

Three-step flow, each step its own request: upload (detect + suggest
mapping), preview (validate, write nothing), commit (apply valid rows,
explicit confirmation). See app/domain/csv_import.py for the parsing/
validation logic and app/domain/positions.py::apply_transaction for how a
validated row actually becomes a Transaction.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db, get_owned_portfolio, require_csrf
from app.config import settings
from app.domain.csv_import import (
    RowResult,
    parse_csv,
    serialize_row_result,
    sniff_delimiter,
    sniff_encoding,
    suggest_column_mapping,
    validate_batch,
)
from app.domain.positions import DuplicateTransactionError, apply_transaction
from app.models import AuditEvent, ImportJob, Instrument, Portfolio, User
from app.schemas.imports import ImportJobOut, ImportJobSummaryOut, ImportPreviewRequest, RowResultOut
from app.schemas.transactions import TransactionCreate

router = APIRouter(prefix="/api/v1/portfolios/{portfolio_id}/imports", tags=["imports"])

# A sample is enough to sniff delimiter/encoding without reading the whole
# (already size-capped) file twice.
_SNIFF_SAMPLE_BYTES = 8192


def _get_owned_job(job_id: str, portfolio: Portfolio, db: Session) -> ImportJob:
    job = db.get(ImportJob, job_id)
    if job is None or job.portfolio_id != portfolio.id:
        raise HTTPException(status_code=404, detail="import job not found")
    return job


def _row_results_out(rows: list[dict] | None) -> list[RowResultOut] | None:
    if rows is None:
        return None
    return [RowResultOut(**row) for row in rows]


def _job_out(job: ImportJob, *, headers=None, suggested_mapping=None, sample_rows=None) -> ImportJobOut:
    return ImportJobOut(
        id=job.id,
        filename=job.filename,
        status=job.status,
        total_rows=job.total_rows,
        valid_count=job.valid_count,
        duplicate_count=job.duplicate_count,
        error_count=job.error_count,
        inserted_count=job.inserted_count,
        created_at=job.created_at,
        previewed_at=job.previewed_at,
        committed_at=job.committed_at,
        delimiter=job.delimiter,
        encoding=job.encoding,
        column_mapping=job.column_mapping,
        suggested_mapping=suggested_mapping,
        headers=headers,
        sample_rows=sample_rows,
        rows=_row_results_out(job.row_results),
    )


@router.post("", response_model=ImportJobOut, status_code=201)
async def upload_import(
    portfolio_id: str,
    file: UploadFile,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    _csrf: None = Depends(require_csrf),
) -> ImportJobOut:
    """specs/PORTFOLIO_IMPORTS.md steps 1-2: upload + limits, detect
    delimiter/encoding/headers. The raw bytes are parsed here and then
    discarded — only the resulting structured rows are kept (see
    ImportJob.raw_rows), never the file itself."""
    portfolio = get_owned_portfolio(portfolio_id, db, user)

    raw_bytes = await file.read(settings.csv_import_max_bytes + 1)
    if len(raw_bytes) > settings.csv_import_max_bytes:
        raise HTTPException(status_code=413, detail=f"file exceeds the {settings.csv_import_max_bytes} byte limit")
    if not raw_bytes:
        raise HTTPException(status_code=422, detail="empty file")

    encoding = sniff_encoding(raw_bytes)
    try:
        text = raw_bytes.decode(encoding)
    except (UnicodeDecodeError, LookupError) as exc:
        raise HTTPException(status_code=422, detail=f"could not decode file as {encoding}") from exc

    delimiter = sniff_delimiter(text[:_SNIFF_SAMPLE_BYTES])
    headers, rows = parse_csv(text, delimiter)
    if not headers:
        raise HTTPException(status_code=422, detail="no header row detected")
    if len(rows) > settings.csv_import_max_rows:
        raise HTTPException(
            status_code=413, detail=f"file has {len(rows)} rows, exceeding the {settings.csv_import_max_rows} limit"
        )

    suggested_mapping = suggest_column_mapping(headers)

    job = ImportJob(
        portfolio_id=portfolio.id,
        user_id=user.id,
        filename=file.filename or "import.csv",
        status="draft",
        delimiter=delimiter,
        encoding=encoding,
        column_mapping=suggested_mapping,
        raw_rows=rows,
        total_rows=len(rows),
    )
    db.add(job)
    db.add(
        AuditEvent(
            user_id=user.id,
            portfolio_id=portfolio.id,
            action="import.upload",
            target_type="import_job",
            event_metadata={"filename": job.filename, "total_rows": job.total_rows},
        )
    )
    db.commit()

    return _job_out(job, headers=headers, suggested_mapping=suggested_mapping, sample_rows=rows[:5])


@router.get("", response_model=list[ImportJobSummaryOut])
def list_imports(
    portfolio_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> list[ImportJobSummaryOut]:
    portfolio = get_owned_portfolio(portfolio_id, db, user)
    jobs = db.scalars(
        select(ImportJob).where(ImportJob.portfolio_id == portfolio.id).order_by(ImportJob.created_at.desc())
    ).all()
    return [ImportJobSummaryOut.model_validate(j, from_attributes=True) for j in jobs]


@router.get("/{job_id}", response_model=ImportJobOut)
def get_import(
    portfolio_id: str, job_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> ImportJobOut:
    portfolio = get_owned_portfolio(portfolio_id, db, user)
    job = _get_owned_job(job_id, portfolio, db)
    return _job_out(job)


def _counts(results: list[RowResult]) -> dict[str, int]:
    counts = {"valid": 0, "duplicate": 0, "error": 0, "inserted": 0}
    for row in results:
        counts[row.status] = counts.get(row.status, 0) + 1
    return counts


@router.post("/{job_id}/preview", response_model=ImportJobOut)
def preview_import(
    portfolio_id: str,
    job_id: str,
    payload: ImportPreviewRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    _csrf: None = Depends(require_csrf),
) -> ImportJobOut:
    """specs/PORTFOLIO_IMPORTS.md steps 3-5: explicit mapping, per-row
    validation, bounded preview. Writes nothing to the portfolio — only the
    job's own report."""
    portfolio = get_owned_portfolio(portfolio_id, db, user)
    job = _get_owned_job(job_id, portfolio, db)
    if job.status == "committed":
        raise HTTPException(status_code=409, detail="this import has already been committed")
    if job.raw_rows is None:
        raise HTTPException(status_code=409, detail="raw rows are no longer available for this job")

    column_mapping = payload.column_mapping or job.column_mapping
    results = validate_batch(db, portfolio, job.raw_rows, column_mapping, payload.default_timezone)

    job.column_mapping = column_mapping
    job.default_timezone = payload.default_timezone
    job.row_results = [serialize_row_result(r) for r in results]
    counts = _counts(results)
    job.valid_count = counts["valid"]
    job.duplicate_count = counts["duplicate"]
    job.error_count = counts["error"]
    job.status = "previewed"
    job.previewed_at = datetime.now(UTC)
    db.commit()

    return _job_out(job)


def _resolve_or_create_instrument(
    db: Session, portfolio: Portfolio, row: RowResult, instrument_cache: dict[str, Instrument]
) -> Instrument | None:
    symbol = row.canonical.get("symbol") if row.canonical else None
    if symbol is None:
        return None
    if symbol in instrument_cache:
        return instrument_cache[symbol]
    existing = db.scalars(
        select(Instrument)
        .where(Instrument.symbol == symbol)
        .where((Instrument.user_id == portfolio.user_id) | (Instrument.user_id.is_(None)))
        .order_by(Instrument.user_id.is_(None))  # the user's own definition wins over the shared catalog
    ).first()
    if existing is not None:
        instrument_cache[symbol] = existing
        return existing
    if row.pending_instrument is None:
        return None
    instrument = Instrument(
        user_id=portfolio.user_id,
        symbol=row.pending_instrument.symbol,
        name=row.pending_instrument.name,
        asset_class=row.pending_instrument.asset_class,
        currency=row.pending_instrument.currency,
    )
    db.add(instrument)
    db.flush()
    instrument_cache[symbol] = instrument
    return instrument


@router.post("/{job_id}/commit", response_model=ImportJobOut)
def commit_import(
    portfolio_id: str,
    job_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    _csrf: None = Depends(require_csrf),
) -> ImportJobOut:
    """specs/PORTFOLIO_IMPORTS.md step 5-6: explicit confirmation. Re-validates
    fresh (a concurrent change since preview could otherwise silently corrupt
    the ledger), applies only rows still valid, and reports the rest — a
    single bad row never aborts the whole file. Purges `raw_rows` afterwards
    (the closest thing to a "raw file" this module ever holds) but keeps the
    report (`row_results`) so it stays downloadable."""
    portfolio = get_owned_portfolio(portfolio_id, db, user)
    job = _get_owned_job(job_id, portfolio, db)
    if job.status == "committed":
        raise HTTPException(status_code=409, detail="this import has already been committed")
    if job.raw_rows is None:
        raise HTTPException(status_code=409, detail="nothing to commit (raw rows unavailable)")

    results = validate_batch(db, portfolio, job.raw_rows, job.column_mapping, job.default_timezone)
    instrument_cache: dict[str, Instrument] = {}
    inserted = 0

    for row in results:
        if row.status != "valid":
            continue
        canonical = row.canonical or {}
        try:
            # A SAVEPOINT per row: a failure here (an unexpected oversell or
            # duplicate caused by a concurrent change since preview) must
            # only undo *this* row - not the rows already applied earlier in
            # this same commit - so one bad row never aborts the batch.
            with db.begin_nested():
                instrument = _resolve_or_create_instrument(db, portfolio, row, instrument_cache)
                payload = TransactionCreate(
                    instrument_id=instrument.id if instrument else None,
                    type=canonical["type"],
                    trade_date=canonical["trade_date"],
                    quantity=canonical.get("quantity", Decimal("0")),
                    unit_price=canonical.get("unit_price", Decimal("0")),
                    currency=canonical.get("currency") or "",
                    fees=canonical.get("fees", Decimal("0")),
                    account=canonical.get("account"),
                    external_id=canonical.get("external_id"),
                    method="Import CSV" if canonical["type"] == "valorisation_privee" else None,
                )
                apply_transaction(db, portfolio, instrument, payload)
        except (DuplicateTransactionError, ValueError) as exc:
            row.status = "error"
            row.messages = [*row.messages, str(exc)]
            instrument_cache.pop(canonical.get("symbol"), None)
            continue
        row.status = "inserted"
        inserted += 1

    job.row_results = [serialize_row_result(r) for r in results]
    counts = _counts(results)
    job.valid_count = counts["valid"]
    job.duplicate_count = counts["duplicate"]
    job.error_count = counts["error"]
    job.inserted_count = inserted
    job.status = "committed"
    job.committed_at = datetime.now(UTC)
    job.raw_rows = None

    db.add(
        AuditEvent(
            user_id=user.id,
            portfolio_id=portfolio.id,
            action="import.commit",
            target_type="import_job",
            target_id=job.id,
            event_metadata={
                "inserted": inserted,
                "duplicates": counts["duplicate"],
                "errors": counts["error"],
            },
        )
    )
    db.commit()

    return _job_out(job)
