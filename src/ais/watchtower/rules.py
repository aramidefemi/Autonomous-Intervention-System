"""Deterministic rules over signals → WatchtowerDecision."""

from ais.models import RiskLevel, WatchtowerAction, WatchtowerDecision
from ais.watchtower.signals import WatchtowerSignals

STALE_AFTER_SECONDS = 300.0
ETA_SLIP_MINUTES = 10.0


def signals_snapshot(signals: WatchtowerSignals) -> dict[str, float | None]:
    return {
        "stalenessSeconds": signals.staleness_seconds,
        "etaDeltaMinutes": signals.eta_delta_minutes,
    }


def decide_from_rules(signals: WatchtowerSignals, *, delivery_id: str) -> WatchtowerDecision:
    snap = signals_snapshot(signals)
    if signals.staleness_seconds is not None and signals.staleness_seconds > STALE_AFTER_SECONDS:
        return WatchtowerDecision(
            deliveryId=delivery_id,
            risk=RiskLevel.HIGH,
            reason="stale_update",
            action=WatchtowerAction.CALL_RIDER,
            action_reason="contact_rider_stale_location",
            signals=snap,
            source="rules",
        )
    if signals.eta_delta_minutes is not None and signals.eta_delta_minutes > ETA_SLIP_MINUTES:
        return WatchtowerDecision(
            deliveryId=delivery_id,
            risk=RiskLevel.MEDIUM,
            reason="eta_slipped",
            action=WatchtowerAction.WAIT,
            action_reason="monitor_after_eta_slip",
            signals=snap,
            source="rules",
        )
    return WatchtowerDecision(
        deliveryId=delivery_id,
        risk=RiskLevel.LOW,
        reason="nominal",
        action=WatchtowerAction.NONE,
        action_reason="",
        signals=snap,
        source="rules",
    )
