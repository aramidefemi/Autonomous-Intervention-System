import pytest

from ais.models import RiskLevel
from ais.watchtower.rules import decide_from_rules
from ais.watchtower.signals import WatchtowerSignals


@pytest.mark.parametrize(
    ("signals", "expected_risk", "expected_reason"),
    [
        (
            WatchtowerSignals(staleness_seconds=400.0, eta_delta_minutes=None),
            RiskLevel.HIGH,
            "stale_update",
        ),
        (
            WatchtowerSignals(staleness_seconds=60.0, eta_delta_minutes=25.0),
            RiskLevel.MEDIUM,
            "eta_slipped",
        ),
        (
            WatchtowerSignals(staleness_seconds=60.0, eta_delta_minutes=5.0),
            RiskLevel.LOW,
            "nominal",
        ),
        (
            WatchtowerSignals(staleness_seconds=None, eta_delta_minutes=None),
            RiskLevel.LOW,
            "nominal",
        ),
    ],
)
def test_rules_matrix(
    signals: WatchtowerSignals,
    expected_risk: RiskLevel,
    expected_reason: str,
) -> None:
    d = decide_from_rules(signals, delivery_id="Dx")
    assert d.risk == expected_risk
    assert d.reason == expected_reason
    assert d.delivery_id == "Dx"
    assert d.source == "rules"
