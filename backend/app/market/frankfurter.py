"""Frankfurter adapter — daily reference exchange rates published by the
European Central Bank, served by an open-source, key-less API
(https://frankfurter.dev). ECB rates are free to reuse with attribution; they
are *reference* rates fixed once per business day (around 16:00 CET), not
tradable quotes — every converted value carries the rate date.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal

from app.market.base import FxProvider, HealthStatus, MarketNotFound, MarketUnavailable, to_decimal
from app.market.http import get_json

BASE_URL = "https://api.frankfurter.dev/v1"
LICENSE_NOTE = (
    "Taux de référence BCE via Frankfurter (open source, sans clé) — un taux par jour ouvré, attribution BCE."
)


def _as_utc_day(value: str) -> datetime:
    d = date.fromisoformat(value)
    return datetime(d.year, d.month, d.day, tzinfo=UTC)


class FrankfurterProvider(FxProvider):
    name = "frankfurter"
    license_note = LICENSE_NOTE
    attribution = "Taux de change : Banque centrale européenne (via Frankfurter)"

    def latest(self, base: str, quotes: list[str]) -> tuple[datetime, dict[str, Decimal]]:
        payload = get_json(self.name, f"{BASE_URL}/latest", params={"base": base, "symbols": ",".join(quotes)})
        if not isinstance(payload, dict) or "rates" not in payload:
            raise MarketUnavailable("frankfurter: unexpected payload")
        rates = {k: v for k, v in ((k, to_decimal(v)) for k, v in payload["rates"].items()) if v is not None}
        if not rates:
            raise MarketNotFound(f"frankfurter: no rate for {base}->{quotes}")
        return _as_utc_day(payload["date"]), rates

    def series(self, base: str, quote: str, start: datetime, end: datetime) -> dict[datetime, Decimal]:
        path = f"{BASE_URL}/{start.date().isoformat()}..{end.date().isoformat()}"
        payload = get_json(self.name, path, params={"base": base, "symbols": quote})
        if not isinstance(payload, dict) or "rates" not in payload:
            raise MarketUnavailable("frankfurter: unexpected payload")
        out: dict[datetime, Decimal] = {}
        for day, rates in payload["rates"].items():
            value = to_decimal(rates.get(quote))
            if value is not None:
                out[_as_utc_day(day)] = value
        return out

    def health(self) -> HealthStatus:
        return HealthStatus(healthy=True, detail="configured (ECB reference rates)")
