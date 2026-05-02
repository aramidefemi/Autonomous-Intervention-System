"""Pure signal extraction from delivery + event history."""

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from ais.models import Delivery


def _utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def _eta_minutes_from_payload(payload: dict[str, Any]) -> float | None:
    for key in ("etaMinutes", "eta_minutes"):
        v = payload.get(key)
        if isinstance(v, (int, float)):
            return float(v)
    return None


@dataclass(frozen=True)
class WatchtowerSignals:
    staleness_seconds: float | None
    eta_delta_minutes: float | None


def compute_signals(
    delivery: Delivery,
    events: list[dict[str, Any]],
    *,
    now: datetime,
) -> WatchtowerSignals:
    staleness: float | None = None
    if delivery.last_updated_at is not None:
        staleness = max(0.0, (_utc(now) - _utc(delivery.last_updated_at)).total_seconds())

    etas: list[float] = []
    for e in events:
        pl = e.get("payload")
        if isinstance(pl, dict):
            eta = _eta_minutes_from_payload(pl)
            if eta is not None:
                etas.append(eta)

    delta: float | None = None
    if len(etas) >= 2:
        delta = etas[-1] - etas[0]

    return WatchtowerSignals(staleness_seconds=staleness, eta_delta_minutes=delta)
