"""Evaluation of informational price alerts.

Reads only what is already stored (latest quote or daily close, previous
close) — it never calls a market provider, so evaluating alerts costs the
same whether they are checked by the worker after each refresh cycle or when
the user opens their notifications. A triggered alert becomes inactive and
produces exactly one in-app Notification; nothing else happens (no e-mail,
no action, no order — specs/PRODUCT_SPEC.md).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.positions import latest_observation, to_decimal
from app.models import ALERT_KINDS, Instrument, Notification, OhlcBar, PriceAlert

KIND_LABELS = {
    "price_above": "cours au-dessus de",
    "price_below": "cours en dessous de",
    "move_pct": "variation quotidienne d'au moins",
}


@dataclass
class Observation:
    price: Decimal
    currency: str
    as_of: datetime
    previous_close: Decimal | None

    @property
    def move_pct(self) -> Decimal | None:
        if self.previous_close is None or self.previous_close == 0:
            return None
        return ((self.price / self.previous_close) - 1) * 100


def current_observation(db: Session, instrument_id: str) -> Observation | None:
    obs = latest_observation(db, instrument_id)
    if obs is None:
        return None
    day_start = obs.as_of.replace(hour=0, minute=0, second=0, microsecond=0)
    previous = db.scalars(
        select(OhlcBar)
        .where(OhlcBar.instrument_id == instrument_id, OhlcBar.as_of < day_start)
        .order_by(OhlcBar.as_of.desc())
        .limit(1)
    ).first()
    return Observation(
        price=obs.price,
        currency=obs.currency,
        as_of=obs.as_of,
        previous_close=to_decimal(previous.close) if previous is not None else None,
    )


def is_triggered(alert: PriceAlert, obs: Observation) -> bool:
    threshold = to_decimal(alert.threshold)
    if alert.kind == "price_above":
        return obs.price >= threshold
    if alert.kind == "price_below":
        return obs.price <= threshold
    if alert.kind == "move_pct":
        move = obs.move_pct
        return move is not None and abs(move) >= threshold
    raise ValueError(f"unknown alert kind {alert.kind!r}")


def _fmt(value: Decimal) -> str:
    """Plain decimal text, trailing zeros trimmed, never scientific notation."""
    text = f"{value:f}"
    return text.rstrip("0").rstrip(".") if "." in text else text


def describe(alert: PriceAlert, instrument: Instrument, obs: Observation) -> tuple[str, str]:
    threshold = to_decimal(alert.threshold)
    if alert.kind == "move_pct":
        move = obs.move_pct or Decimal("0")
        title = f"{instrument.symbol} : variation de {move:+.2f} % sur la journée"
        body = (
            f"Seuil de ±{_fmt(threshold)} % atteint. Dernier cours {_fmt(obs.price)} {obs.currency} "
            f"(observé le {obs.as_of:%d/%m/%Y %H:%M} UTC)."
        )
    else:
        direction = "au-dessus" if alert.kind == "price_above" else "en dessous"
        title = f"{instrument.symbol} : cours {direction} de {_fmt(threshold)} {obs.currency}"
        body = f"Dernier cours {_fmt(obs.price)} {obs.currency}, observé le {obs.as_of:%d/%m/%Y %H:%M} UTC."
    if alert.note:
        body += f" Note : {alert.note}"
    return title[:200], body[:500]


def evaluate_alerts(db: Session, user_id: str | None = None) -> int:
    """Evaluates every active alert (or one user's) against stored data and
    writes a notification per trigger. Returns the number triggered. Commits."""
    query = select(PriceAlert).where(PriceAlert.active.is_(True))
    if user_id is not None:
        query = query.where(PriceAlert.user_id == user_id)
    alerts = db.scalars(query.order_by(PriceAlert.created_at)).all()
    now = datetime.now(UTC)
    observations: dict[str, Observation | None] = {}
    triggered = 0
    for alert in alerts:
        if alert.instrument_id not in observations:
            observations[alert.instrument_id] = current_observation(db, alert.instrument_id)
        obs = observations[alert.instrument_id]
        alert.last_evaluated_at = now
        if obs is None:
            continue
        alert.last_value = obs.price
        if not is_triggered(alert, obs):
            continue
        instrument = db.get(Instrument, alert.instrument_id)
        if instrument is None:
            continue
        title, body = describe(alert, instrument, obs)
        alert.active = False
        alert.triggered_at = now
        db.add(
            Notification(
                user_id=alert.user_id,
                instrument_id=alert.instrument_id,
                alert_id=alert.id,
                kind=alert.kind,
                title=title,
                body=body,
            )
        )
        triggered += 1
    db.commit()
    return triggered


def purge_old_notifications(db: Session, keep_days: int = 90) -> int:
    """Worker housekeeping: read notifications older than `keep_days` are
    dropped (specs/SECURITY.md: minimal retention). Commits."""
    cutoff = datetime.now(UTC) - timedelta(days=keep_days)
    old = db.scalars(select(Notification).where(Notification.read_at.is_not(None), Notification.created_at < cutoff))
    n = 0
    for notification in old:
        db.delete(notification)
        n += 1
    db.commit()
    return n


__all__ = [
    "ALERT_KINDS",
    "KIND_LABELS",
    "Observation",
    "current_observation",
    "evaluate_alerts",
    "is_triggered",
    "purge_old_notifications",
]
