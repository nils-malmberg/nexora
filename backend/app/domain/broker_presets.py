"""Broker export profiles ("presets") for the CSV import.

Trade Republic and Revolut have no public read-only API for personal
accounts; the supported, secure path is the export their apps provide,
imported here. A preset recognises an export by its header row and rewrites
each row into the canonical import schema (see app/domain/csv_import.py) —
labels, sign conventions, currency symbols, ISIN vs ticker. Everything the
preset cannot express (a split without ratio, an unknown label) is kept as a
reported, skipped row (`SKIP_KEY`) rather than guessed or silently dropped.

Formats are matched on header *names*, never assumed from the file name, and
the preview step always shows the user what was understood before anything
is written.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation

SKIP_KEY = "__skip__"


def _norm(value: str) -> str:
    value = unicodedata.normalize("NFKD", value or "").encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")


def _money(value: str | None) -> Decimal | None:
    if value is None:
        return None
    cleaned = re.sub(r"[€$£¥  \s]", "", value.strip())
    if not cleaned:
        return None
    if "," in cleaned and "." in cleaned:
        if cleaned.rfind(",") > cleaned.rfind("."):
            cleaned = cleaned.replace(".", "").replace(",", ".")
        else:
            cleaned = cleaned.replace(",", "")
    elif "," in cleaned:
        cleaned = cleaned.replace(",", ".")
    try:
        return Decimal(cleaned)
    except InvalidOperation:
        return None


def _fmt(value: Decimal | None) -> str:
    return "" if value is None else format(value.normalize(), "f")


def _cash(base: dict[str, str], kind: str, amount: Decimal | None) -> dict[str, str]:
    """A cash-only row (no instrument): quantity 1, unit_price = amount."""
    return {
        **base,
        "symbol": "",
        "isin": "",
        "asset_class": "",
        "type": kind,
        "quantity": "1",
        "unit_price": _fmt(abs(amount or Decimal(0))),
    }


@dataclass
class Preset:
    key: str
    label: str
    instructions: list[str]
    required_headers: list[set[str]]  # each entry: a set of accepted normalized names for one required column
    notes: list[str] = field(default_factory=list)

    def matches(self, headers: list[str]) -> bool:
        normalized = {_norm(h) for h in headers}
        return all(normalized & accepted for accepted in self.required_headers)

    def transform(self, rows: list[dict[str, str]], headers: list[str]) -> list[dict[str, str]]:  # pragma: no cover
        raise NotImplementedError


def _column(headers: list[str], accepted: set[str]) -> str | None:
    for header in headers:
        if _norm(header) in accepted:
            return header
    return None


# ---------------------------------------------------------------------------
# Revolut — "Trading account statement" CSV
# ---------------------------------------------------------------------------

_REV_DATE = {"date"}
_REV_TICKER = {"ticker"}
_REV_TYPE = {"type"}
_REV_QTY = {"quantity"}
_REV_PRICE = {"price_per_share"}
_REV_TOTAL = {"total_amount"}
_REV_CCY = {"currency"}


class RevolutPreset(Preset):
    def __init__(self) -> None:
        super().__init__(
            key="revolut",
            label="Revolut (relevé du compte titres)",
            instructions=[
                "Dans l'app Revolut : Investir › (⋯) › Relevés › « Relevé du compte » (Account statement).",
                "Choisissez la période, le format CSV (ou Excel puis enregistrez en CSV) et téléchargez le fichier.",
                "Importez-le ici : les achats, ventes, dividendes, dépôts, retraits et frais de garde sont reconnus.",
            ],
            required_headers=[_REV_DATE, _REV_TICKER, _REV_TYPE, _REV_QTY, _REV_PRICE, _REV_TOTAL, _REV_CCY],
            notes=[
                "Les splits et opérations sur titres sont signalés mais non importés (ratio non fourni).",
                "Les tickers Revolut sont des symboles US (ex. AAPL) ; les titres européens sont résolus par symbole.",
            ],
        )

    def transform(self, rows: list[dict[str, str]], headers: list[str]) -> list[dict[str, str]]:
        c_date = _column(headers, _REV_DATE)
        c_ticker = _column(headers, _REV_TICKER)
        c_type = _column(headers, _REV_TYPE)
        c_qty = _column(headers, _REV_QTY)
        c_price = _column(headers, _REV_PRICE)
        c_total = _column(headers, _REV_TOTAL)
        c_ccy = _column(headers, _REV_CCY)
        out: list[dict[str, str]] = []
        for row in rows:
            kind = _norm(row.get(c_type, ""))
            ticker = (row.get(c_ticker) or "").strip().upper()
            total = _money(row.get(c_total))
            qty = _money(row.get(c_qty))
            price = _money(row.get(c_price))
            base = {
                "date": (row.get(c_date) or "").strip(),
                "currency": (row.get(c_ccy) or "").strip().upper(),
                "symbol": ticker,
                "asset_class": "action" if ticker else "",
                "fees": "0",
                "note": (row.get(c_type) or "").strip(),
            }
            if kind.startswith("buy") or kind.startswith("sell"):
                if qty is None or price is None:
                    out.append({**base, SKIP_KEY: "quantité ou prix manquant"})
                    continue
                trade = "achat" if kind.startswith("buy") else "vente"
                out.append({**base, "type": trade, "quantity": _fmt(abs(qty)), "unit_price": _fmt(abs(price))})
            elif kind == "dividend":
                out.append({**base, "type": "dividende", "quantity": "1", "unit_price": _fmt(abs(total or Decimal(0)))})
            elif kind in ("cash_top_up", "top_up"):
                out.append(_cash(base, "depot", total))
            elif kind in ("cash_withdrawal", "withdrawal"):
                out.append(_cash(base, "retrait", total))
            elif kind in ("custody_fee", "fee"):
                out.append(_cash(base, "frais", total))
            elif kind in ("interest", "savings_interest"):
                out.append(_cash(base, "interet", total))
            else:
                label = row.get(c_type, "")
                out.append({**base, SKIP_KEY: f"type Revolut « {label} » non pris en charge (à saisir manuellement)"})
        return out


# ---------------------------------------------------------------------------
# Trade Republic — transaction export (Profil › Historique › Exporter)
# ---------------------------------------------------------------------------

_TR_DATE = {"datum", "date"}
_TR_TYPE = {"typ", "type"}
_TR_VALUE = {"wert", "value", "valeur", "montant", "amount"}
_TR_ISIN = {"isin"}
_TR_SHARES = {"anzahl", "shares", "quantite", "quantity", "stuck"}
_TR_FEES = {"gebuhren", "fees", "frais"}
_TR_TAX = {"steuern", "tax", "taxes", "impots"}
_TR_NOTE = {"notiz", "note", "description"}

_TR_KINDS = {
    "kauf": "achat",
    "buy": "achat",
    "achat": "achat",
    "sparplan": "achat",
    "savings_plan": "achat",
    "plan_d_epargne": "achat",
    "verkauf": "vente",
    "sell": "vente",
    "vente": "vente",
    "dividende": "dividende",
    "dividend": "dividende",
    "zinsen": "interet",
    "interest": "interet",
    "interets": "interet",
    "einzahlung": "depot",
    "deposit": "depot",
    "depot": "depot",
    "auszahlung": "retrait",
    "withdrawal": "retrait",
    "retrait": "retrait",
    "gebuhren": "frais",
    "fees": "frais",
    "fee": "frais",
    "frais": "frais",
}


class TradeRepublicPreset(Preset):
    def __init__(self) -> None:
        super().__init__(
            key="trade_republic",
            label="Trade Republic (export des transactions)",
            instructions=[
                "Dans l'app Trade Republic : Profil › Historique (ou Transactions) › Exporter › période › CSV.",
                "Le fichier contient une ligne par opération : ISIN du titre, quantité, valeur et frais.",
                "Importez-le ici : les titres sont retrouvés par ISIN dans le catalogue "
                "(une recherche par ISIN est faite si besoin).",
            ],
            required_headers=[_TR_DATE, _TR_TYPE, _TR_VALUE, _TR_ISIN, _TR_SHARES],
            notes=[
                "Le prix unitaire est déduit : valeur ÷ quantité (frais exclus).",
                "Les impôts prélevés à la source sont enregistrés comme frais.",
                "Colonnes attendues (allemand, anglais ou français) : Datum/Date, Typ/Type, Wert/Value, "
                "Notiz/Note, ISIN, Anzahl/Shares, Gebühren/Fees, Steuern/Tax.",
            ],
        )

    def transform(self, rows: list[dict[str, str]], headers: list[str]) -> list[dict[str, str]]:
        c_date = _column(headers, _TR_DATE)
        c_type = _column(headers, _TR_TYPE)
        c_value = _column(headers, _TR_VALUE)
        c_isin = _column(headers, _TR_ISIN)
        c_shares = _column(headers, _TR_SHARES)
        c_fees = _column(headers, _TR_FEES)
        c_tax = _column(headers, _TR_TAX)
        c_note = _column(headers, _TR_NOTE)
        out: list[dict[str, str]] = []
        for row in rows:
            raw_kind = (row.get(c_type) or "").strip()
            kind = _TR_KINDS.get(_norm(raw_kind))
            isin = (row.get(c_isin) or "").strip().upper()
            value = _money(row.get(c_value))
            shares = _money(row.get(c_shares)) if c_shares else None
            fees = abs(_money(row.get(c_fees)) or Decimal(0)) if c_fees else Decimal(0)
            tax = abs(_money(row.get(c_tax)) or Decimal(0)) if c_tax else Decimal(0)
            base = {
                "date": (row.get(c_date) or "").strip(),
                "currency": "EUR",  # Trade Republic accounts and exports are in EUR
                "isin": isin,
                "symbol": "",
                "asset_class": "",
                "fees": _fmt(fees + tax),
                "note": ((row.get(c_note) or "").strip() or raw_kind)[:500],
            }
            if kind is None:
                out.append(
                    {**base, SKIP_KEY: f"type Trade Republic « {raw_kind} » non pris en charge (à saisir à la main)"}
                )
                continue
            if kind in ("achat", "vente"):
                if not shares or value is None:
                    out.append({**base, SKIP_KEY: "quantité ou valeur manquante"})
                    continue
                gross = abs(value)
                # Value is the cash actually moved (fees included): back out
                # the fees so unit_price × quantity is the pure trade amount.
                net = gross - fees if kind == "achat" else gross + fees
                unit_price = (net / abs(shares)).quantize(Decimal("0.000001")) if net > 0 else Decimal(0)
                trade = {**base, "type": kind, "asset_class": "action", "quantity": _fmt(abs(shares))}
                out.append({**trade, "unit_price": _fmt(unit_price)})
            elif kind == "dividende":
                dividend = {**base, "type": "dividende", "asset_class": "action", "quantity": "1"}
                out.append({**dividend, "unit_price": _fmt(abs(value or Decimal(0)))})
            else:  # interet / depot / retrait / frais: no instrument
                out.append(_cash(base, kind, value))
        return out


PRESETS: dict[str, Preset] = {p.key: p for p in (TradeRepublicPreset(), RevolutPreset())}

# The canonical schema produced by every preset: an identity column mapping.
PRESET_MAPPING = {
    "date": "date",
    "type": "type",
    "symbol": "symbol",
    "isin": "isin",
    "asset_class": "asset_class",
    "quantity": "quantity",
    "unit_price": "unit_price",
    "currency": "currency",
    "fees": "fees",
    "note": "note",
}


def detect_preset(headers: list[str]) -> Preset | None:
    for preset in PRESETS.values():
        if preset.matches(headers):
            return preset
    return None


def apply_preset(preset_key: str | None, rows: list[dict[str, str]], headers: list[str]) -> list[dict[str, str]]:
    if not preset_key:
        return rows
    preset = PRESETS[preset_key]
    return preset.transform(rows, headers)


def describe_presets() -> list[dict]:
    return [
        {"key": p.key, "label": p.label, "instructions": p.instructions, "notes": p.notes} for p in PRESETS.values()
    ]
