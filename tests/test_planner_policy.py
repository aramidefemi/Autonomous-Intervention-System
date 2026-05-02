"""Matrix: watchtower decision → intervention plan."""

from datetime import UTC, datetime

import pytest

from ais.models import InterventionType, RiskLevel, WatchtowerDecision
from ais.planner.policy import intervention_plan_from_decision


@pytest.mark.parametrize(
    ("risk", "wt_reason", "expected_type"),
    [
        (RiskLevel.LOW, "nominal", None),
        (RiskLevel.MEDIUM, "eta_slipped", InterventionType.WAIT),
        (RiskLevel.HIGH, "stale_update", InterventionType.CALL_RIDER),
        (RiskLevel.HIGH, "other", InterventionType.ESCALATE),
    ],
)
def test_policy_matrix(
    risk: RiskLevel,
    wt_reason: str,
    expected_type: InterventionType | None,
) -> None:
    t = datetime(2026, 5, 2, 12, 0, 0, tzinfo=UTC)
    d = WatchtowerDecision(
        deliveryId="D-1",
        risk=risk,
        reason=wt_reason,
        signals={},
    )
    plan = intervention_plan_from_decision(d, planned_at=t)
    if expected_type is None:
        assert plan is None
    else:
        assert plan is not None
        assert plan.intervention_type == expected_type
        assert plan.delivery_id == "D-1"
        assert plan.watchtower_risk == risk
        assert plan.watchtower_reason == wt_reason
