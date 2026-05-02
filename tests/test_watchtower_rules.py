import pytest

from ais.models import RiskLevel, WatchtowerAction
from ais.watchtower.rules import decide_from_rules
from ais.watchtower.signals import WatchtowerSignals


@pytest.mark.parametrize(
    ("signals", "expected_risk", "expected_reason", "expected_action"),
    [
        (
            WatchtowerSignals(staleness_seconds=400.0, eta_delta_minutes=None),
            RiskLevel.HIGH,
            "stale_update",
            WatchtowerAction.CALL_RIDER,
        ),
        (
            WatchtowerSignals(staleness_seconds=60.0, eta_delta_minutes=25.0),
            RiskLevel.MEDIUM,
            "eta_slipped",
            WatchtowerAction.WAIT,
        ),
        (
            WatchtowerSignals(staleness_seconds=60.0, eta_delta_minutes=5.0),
            RiskLevel.LOW,
            "nominal",
            WatchtowerAction.NONE,
        ),
        (
            WatchtowerSignals(staleness_seconds=None, eta_delta_minutes=None),
            RiskLevel.LOW,
            "nominal",
            WatchtowerAction.NONE,
        ),
    ],
)
def test_rules_matrix(
    signals: WatchtowerSignals,
    expected_risk: RiskLevel,
    expected_reason: str,
    expected_action: WatchtowerAction,
) -> None:
    d = decide_from_rules(signals, delivery_id="Dx")
    assert d.risk == expected_risk
    assert d.reason == expected_reason
    assert d.action == expected_action
    assert d.delivery_id == "Dx"
    assert d.source == "rules"
