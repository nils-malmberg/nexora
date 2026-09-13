"""CSV import parsing, mapping and row-by-row validation.

Implements the parcours described in specs/PORTFOLIO_IMPORTS.md: sniff
delimiter/encoding/headers, suggest a column mapping, validate every row
(date/decimal parsing, transaction shape rules, sell-short and duplicate
detection), and only ever *report* — nothing is written to the database from
this module. `app/api/routers/imports.py` is what actually applies valid rows,
via `app.domain.positions.apply_transaction` (the same path the manual
transaction API uses).

The raw uploaded bytes are never written to disk or kept as-is anywhere —
only the already-structured rows produced by `parse_csv` are held (briefly,
in `ImportJob.raw_rows`), and even those are dropped once a job is committed.
"""

from __future__ import annotations

import csv
import hashlib
import io
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from charset_normalizer import from_bytes
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.positions import (
    LOT_AFFECTING_TYPES,
    existing_lot_transactions,
    quantize_money,
    quantize_quantity,
    replay_lots,
    to_decimal,
)
from app.models import ASSET_CLASSES, Instrument, Portfolio, Transaction
from app.schemas.transactions import (
    CASH_ONLY_NO_INSTRUMENT_TYPES,
    INSTRUMENT_REQUIRED_TYPES,
    TransactionCreate,
)

CANONICAL_FIELDS = (
    "date",
    "type",
    "symbol",
    "asset_class",
    "quantity",
    "unit_price",
    "currency",
    "fees",
    "account",
    "external_id",
)

_SYNONYMS: dict[str, set[str]] = {
    "date": {"date", "trade_date", "date_operation", "date_transaction", "jour"},
    "type": {"type", "type_transaction", "operation", "nature"},
    "symbol": {"symbol", "ticker", "isin", "titre", "valeur"},
    "asset_class": {"asset_class", "classe_actif", "classe_d_actif", "categorie"},
    "quantity": {"quantity", "quantite", "qty", "nombre"},
    "unit_price": {"unit_price", "prix_unitaire", "prix", "montant", "amount", "cours"},
    "currency": {"currency", "devise"},
    "fees": {"fees", "frais", "commission"},
    "account": {"account", "compte"},
    "external_id": {"external_id", "id_externe", "reference", "ref", "id"},
}

_DATE_FORMATS = ("%Y-%m-%d", "%d/%m/%Y", "%Y-%m-%d %H:%M:%S", "%d/%m/%Y %H:%M", "%m/%d/%Y")


def _normalize_token(value: str) -> str:
    """Lowercase, accent-stripped, non-alphanumeric-collapsed-to-underscore
    form — used both for matching a CSV header to a canonical field and for
    matching a CSV type value (e.g. "Dépôt", "Valorisation privée") to our
    (already-French) TRANSACTION_TYPES."""
    normalized = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]+", "_", normalized.lower()).strip("_")


def sniff_encoding(raw_bytes: bytes) -> str:
    match = from_bytes(raw_bytes).best()
    return match.encoding if match else "utf-8"


def sniff_delimiter(sample_text: str) -> str:
    try:
        return csv.Sniffer().sniff(sample_text, delimiters=",;\t|").delimiter
    except csv.Error:
        return ","


def parse_csv(text: str, delimiter: str) -> tuple[list[str], list[dict[str, str]]]:
    reader = csv.DictReader(io.StringIO(text), delimiter=delimiter)
    headers = reader.fieldnames or []
    rows = [dict(row) for row in reader]
    return list(headers), rows


def suggest_column_mapping(headers: list[str]) -> dict[str, str]:
    """canonical field -> original CSV header, best-effort. Never guesses
    silently past this: an unmapped canonical field just stays unmapped, and
    a row missing a value it needs is reported as an error, not inferred —
    specs/PORTFOLIO_IMPORTS.md: "Ne pas déduire silencieusement"."""
    normalized_headers = {header: _normalize_token(header) for header in headers}
    mapping: dict[str, str] = {}
    for canonical_field in CANONICAL_FIELDS:
        for header, normalized in normalized_headers.items():
            if normalized in _SYNONYMS[canonical_field]:
                mapping[canonical_field] = header
                break
    return mapping


def parse_decimal(value: str, field_label: str) -> Decimal:
    cleaned = value.strip().replace(" ", "").replace(" ", "")
    if "," in cleaned and "." in cleaned:
        # Whichever separator appears last is the decimal point (EU
        # "1.234,56" vs US "1,234.56"); the other is a thousands separator.
        if cleaned.rfind(",") > cleaned.rfind("."):
            cleaned = cleaned.replace(".", "").replace(",", ".")
        else:
            cleaned = cleaned.replace(",", "")
    elif "," in cleaned:
        cleaned = cleaned.replace(",", ".")  # comma = decimal separator
    try:
        return Decimal(cleaned)
    except InvalidOperation as exc:
        raise ValueError(f"{field_label} invalide : {value!r}") from exc


def parse_date(value: str, default_timezone: str) -> datetime:
    value = value.strip()
    parsed: datetime | None = None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        for fmt in _DATE_FORMATS:
            try:
                parsed = datetime.strptime(value, fmt)
                break
            except ValueError:
                continue
    if parsed is None:
        raise ValueError(f"date invalide : {value!r}")
    if parsed.tzinfo is None:
        try:
            tz = ZoneInfo(default_timezone)
        except ZoneInfoNotFoundError as exc:
            raise ValueError(f"fuseau horaire inconnu : {default_timezone!r}") from exc
        parsed = parsed.replace(tzinfo=tz)
    return parsed.astimezone(UTC)


def compute_fingerprint(
    portfolio_id: str,
    type_: str,
    trade_date: datetime,
    instrument_key: str | None,
    quantity: Decimal,
    unit_price: Decimal,
    currency: str,
    fees: Decimal,
    account: str | None,
) -> str:
    """Empreinte canonique pour la déduplication sans `external_id` —
    specs/PORTFOLIO_IMPORTS.md. Un doublon exact (mêmes champs) sur une
    ré-importation est reconnu ; deux instruments distincts qui n'existent
    pas encore et partagent le même symbole au sein d'un même lot utilisent
    ce symbole comme clé (voir validate_batch), pas un futur id réel.

    Amounts are quantized to the same scale `apply_transaction` stores them
    at (see app.domain.positions) before hashing: a freshly parsed "1" and a
    value round-tripped through the Numeric(24,8) `quantity` column
    ("1.00000000") are the same transaction and must produce the same
    fingerprint, not two different strings."""
    raw = "|".join(
        [
            portfolio_id,
            type_,
            trade_date.isoformat(),
            instrument_key or "",
            str(quantize_quantity(to_decimal(quantity))),
            str(quantize_money(to_decimal(unit_price))),
            currency,
            str(quantize_money(to_decimal(fees))),
            account or "",
        ]
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


@dataclass
class PendingInstrument:
    symbol: str
    name: str
    asset_class: str
    currency: str


@dataclass
class RowResult:
    row_number: int
    status: str  # "valid" | "duplicate" | "error" | "inserted"
    messages: list[str] = field(default_factory=list)
    canonical: dict[str, Any] | None = None  # rich Python types (Decimal/datetime) - see serialize_row_result
    pending_instrument: PendingInstrument | None = None


def serialize_row_result(row: RowResult) -> dict:
    canonical = None
    if row.canonical is not None:
        canonical = {
            key: (value.isoformat() if isinstance(value, datetime) else str(value) if value is not None else None)
            for key, value in row.canonical.items()
        }
    return {
        "row_number": row.row_number,
        "status": row.status,
        "messages": row.messages,
        "canonical": canonical,
    }


def _canonicalize(
    raw_row: dict[str, str], column_mapping: dict[str, str], default_timezone: str
) -> tuple[dict[str, Any], list[str]]:
    errors: list[str] = []

    def get(field_name: str) -> str | None:
        header = column_mapping.get(field_name)
        if not header:
            return None
        value = raw_row.get(header)
        return value.strip() if value else None

    canonical: dict[str, Any] = {}

    raw_type = get("type")
    canonical["type"] = _normalize_token(raw_type) if raw_type else None

    raw_date = get("date")
    if not raw_date:
        errors.append("date manquante")
    else:
        try:
            canonical["trade_date"] = parse_date(raw_date, default_timezone)
        except ValueError as exc:
            errors.append(str(exc))

    for field_name, label in (("quantity", "quantity"), ("unit_price", "unit_price"), ("fees", "fees")):
        raw_value = get(field_name)
        if raw_value in (None, ""):
            if field_name == "fees":
                canonical["fees"] = Decimal("0")
            continue
        try:
            canonical[field_name] = parse_decimal(raw_value, label)
        except ValueError as exc:
            errors.append(str(exc))

    symbol = get("symbol")
    canonical["symbol"] = symbol.upper() if symbol else None
    asset_class = get("asset_class")
    canonical["asset_class"] = _normalize_token(asset_class) if asset_class else None
    currency = get("currency")
    canonical["currency"] = currency.upper() if currency else None
    canonical["account"] = get("account")
    canonical["external_id"] = get("external_id")

    return canonical, errors


def validate_batch(
    db: Session,
    portfolio: Portfolio,
    raw_rows: list[dict[str, str]],
    column_mapping: dict[str, str],
    default_timezone: str = "UTC",
) -> list[RowResult]:
    """Validates every row; writes nothing. See module docstring."""
    # Shared catalog entries first, then the user's own (which win on a
    # symbol clash: a private "AAPL" the user defined is what *their* CSV means).
    existing_instruments: dict[str, Instrument] = {}
    for instrument in db.scalars(
        select(Instrument)
        .where((Instrument.user_id.is_(None)) | (Instrument.user_id == portfolio.user_id))
        .order_by(Instrument.user_id.is_(None).desc())
    ):
        existing_instruments[instrument.symbol] = instrument
    existing_external_ids = set(
        db.scalars(
            select(Transaction.external_id).where(
                Transaction.portfolio_id == portfolio.id, Transaction.external_id.is_not(None)
            )
        )
    )
    existing_fingerprints = {
        compute_fingerprint(
            portfolio.id,
            tx.type,
            tx.trade_date,
            tx.instrument_id,
            tx.quantity,
            tx.unit_price,
            tx.currency,
            tx.fees,
            tx.account,
        )
        for tx in db.scalars(select(Transaction).where(Transaction.portfolio_id == portfolio.id))
    }

    seen_external_ids: set[str] = set()
    seen_fingerprints: set[str] = set()
    pending_instruments: dict[str, PendingInstrument] = {}
    # instrument_key (real id, or "NEW:<symbol>" for a not-yet-created one) -> running transaction list
    lot_state_cache: dict[str, list[Transaction]] = {}

    results: list[RowResult] = []

    for row_number, raw_row in enumerate(raw_rows, start=1):
        canonical, parse_errors = _canonicalize(raw_row, column_mapping, default_timezone)
        if parse_errors:
            results.append(RowResult(row_number, "error", parse_errors, canonical))
            continue

        row_type = canonical.get("type")
        # A placeholder is enough here: TransactionCreate only checks whether
        # instrument_id is set at all for this type, never that it resolves
        # to a real row (that happens below, separately, with auto-create).
        shape_instrument_id = (
            None if row_type in CASH_ONLY_NO_INSTRUMENT_TYPES else (canonical.get("symbol") or "placeholder")
        )
        try:
            TransactionCreate(
                instrument_id=shape_instrument_id,
                type=row_type or "",
                trade_date=canonical["trade_date"],
                quantity=canonical.get("quantity", Decimal("0")),
                unit_price=canonical.get("unit_price", Decimal("0")),
                currency=canonical.get("currency") or "",
                fees=canonical.get("fees", Decimal("0")),
                account=canonical.get("account"),
                external_id=canonical.get("external_id"),
                method="Import CSV" if row_type == "valorisation_privee" else None,
            )
        except ValidationError as exc:
            messages = [e["msg"] for e in exc.errors()]
            results.append(RowResult(row_number, "error", messages, canonical))
            continue

        # Duplicate detection - never an error, always skips the row.
        external_id = canonical.get("external_id")
        if external_id:
            if external_id in existing_external_ids or external_id in seen_external_ids:
                seen_external_ids.add(external_id)
                results.append(
                    RowResult(row_number, "duplicate", [f"external_id {external_id!r} déjà utilisé"], canonical)
                )
                continue
            seen_external_ids.add(external_id)

        # Instrument resolution (only for types that need one).
        instrument: Instrument | None = None
        instrument_key: str | None = None
        messages: list[str] = []
        if row_type in INSTRUMENT_REQUIRED_TYPES:
            symbol = canonical.get("symbol")
            instrument = existing_instruments.get(symbol) if symbol else None
            if instrument is not None:
                instrument_key = instrument.id
            elif symbol in pending_instruments:
                # Already introduced by an earlier row in this same batch -
                # later rows for the same new symbol don't need to repeat
                # asset_class/currency (and won't re-flag the auto-create).
                instrument_key = f"NEW:{symbol}"
            else:
                asset_class = canonical.get("asset_class")
                currency = canonical.get("currency")
                if asset_class not in ASSET_CLASSES or not currency:
                    results.append(
                        RowResult(
                            row_number,
                            "error",
                            [f"instrument {symbol!r} inconnu et asset_class/currency insuffisants pour le créer"],
                            canonical,
                        )
                    )
                    continue
                instrument_key = f"NEW:{symbol}"
                pending_instruments[symbol] = PendingInstrument(
                    symbol=symbol, name=symbol, asset_class=asset_class, currency=currency
                )
                messages.append(f"instrument {symbol!r} sera créé automatiquement à la confirmation")

        if not external_id:
            fingerprint = compute_fingerprint(
                portfolio.id,
                row_type,
                canonical["trade_date"],
                instrument_key,
                canonical.get("quantity", Decimal("0")),
                canonical.get("unit_price", Decimal("0")),
                canonical.get("currency") or "",
                canonical.get("fees", Decimal("0")),
                canonical.get("account"),
            )
            if fingerprint in existing_fingerprints or fingerprint in seen_fingerprints:
                seen_fingerprints.add(fingerprint)
                results.append(
                    RowResult(row_number, "duplicate", ["ligne identique déjà importée (empreinte)"], canonical)
                )
                continue
            seen_fingerprints.add(fingerprint)

        # Sell-short / bad-split detection: replay this instrument's existing
        # transactions plus every valid batch row seen so far.
        if row_type in LOT_AFFECTING_TYPES and instrument_key:
            running = lot_state_cache.get(instrument_key)
            if running is None:
                running = existing_lot_transactions(db, portfolio.id, instrument.id) if instrument else []
                lot_state_cache[instrument_key] = running
            candidate = Transaction(
                id=f"row-{row_number}",
                type=row_type,
                trade_date=canonical["trade_date"],
                quantity=canonical.get("quantity", Decimal("0")),
                unit_price=canonical.get("unit_price", Decimal("0")),
                fees=canonical.get("fees", Decimal("0")),
                currency=canonical.get("currency") or "",
            )
            try:
                replay_lots([*running, candidate])
            except ValueError as exc:
                results.append(RowResult(row_number, "error", [str(exc)], canonical))
                continue
            running.append(candidate)

        pending = pending_instruments.get(canonical.get("symbol")) if instrument is None and instrument_key else None
        results.append(RowResult(row_number, "valid", messages, canonical, pending_instrument=pending))

    return results
