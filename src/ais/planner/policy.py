"""Pure mapping: watchtower decision → intervention plan or skip."""

from datetime import datetime

from ais.models import InterventionPlan, InterventionType, RiskLevel, WatchtowerDecision


def intervention_plan_from_decision(
    decision: WatchtowerDecision,
    *,
    planned_at: datetime,
) -> InterventionPlan | None:
    """Rules-only policy: risk + watchtower reason → plan; LOW/nominal → no plan."""
    itype, reason = _select_type_and_reason(decision)
    if itype is None:
        return None
    return InterventionPlan(
        deliveryId=decision.delivery_id,
        interventionType=itype,
        reason=reason,
        plannedAt=planned_at,
        watchtowerRisk=decision.risk,
        watchtowerReason=decision.reason,
        source="rules",
    )


def _select_type_and_reason(d: WatchtowerDecision) -> tuple[InterventionType | None, str]:
    if d.risk == RiskLevel.LOW:
        return None, ""
    if d.risk == RiskLevel.MEDIUM:
        return InterventionType.WAIT, "monitor_after_eta_slip"
    # HIGH
    if d.reason == "stale_update":
        return InterventionType.CALL_RIDER, "contact_rider_stale_location"
    return InterventionType.ESCALATE, "high_risk_escalate"
