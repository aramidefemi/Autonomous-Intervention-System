import json
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from ais.models import (
    AgentDecision,
    Delivery,
    InterventionPlan,
    InterventionType,
    IssueType,
    NormalizedEvent,
    RiskLevel,
    VoiceSessionOutcome,
    WatchtowerAction,
    WatchtowerDecision,
)


def test_delivery_round_trip() -> None:
    d = Delivery(
        deliveryId="D-1",
        status="in_transit",
        lastUpdatedAt=datetime(2025, 1, 1, 12, 0, 0, tzinfo=UTC),
    )
    data = d.model_dump(by_alias=True, mode="json")
    d2 = Delivery.model_validate(data)
    assert d2.delivery_id == "D-1"
    assert json.dumps(data)


def test_normalized_event_invalid_schema() -> None:
    with pytest.raises(ValidationError):
        NormalizedEvent(
            deliveryId="D-1",
            eventType="location",
            schemaVersion=999,
        )


def test_agent_decision_bounds() -> None:
    with pytest.raises(ValidationError):
        AgentDecision(
            deliveryId="D-1",
            agentName="watchtower",
            confidence=1.5,
        )


def test_watchtower_decision_round_trip() -> None:
    w = WatchtowerDecision(
        deliveryId="D-1",
        risk=RiskLevel.LOW,
        reason="nominal",
        action=WatchtowerAction.NONE,
        signals={"stalenessSeconds": 1.0},
    )
    data = w.model_dump(by_alias=True, mode="json")
    w2 = WatchtowerDecision.model_validate(data)
    assert w2.risk == RiskLevel.LOW
    assert w2.action == WatchtowerAction.NONE
    assert w2.signals["stalenessSeconds"] == 1.0


def test_intervention_plan_round_trip() -> None:
    p = InterventionPlan(
        deliveryId="D-1",
        interventionType=InterventionType.WAIT,
        reason="monitor_after_eta_slip",
        watchtowerRisk=RiskLevel.MEDIUM,
        watchtowerReason="eta_slipped",
    )
    data = p.model_dump(by_alias=True, mode="json")
    p2 = InterventionPlan.model_validate(data)
    assert p2.intervention_type == InterventionType.WAIT


def test_voice_session_outcome_round_trip() -> None:
    v = VoiceSessionOutcome(
        deliveryId="D-1",
        roomName="r1",
        transcript="test",
        issueType=IssueType.MECHANICAL_FAILURE,
        lifecycle="completed",
        extractionConfidence=0.9,
        extractionMethod="keyword",
    )
    data = v.model_dump(by_alias=True, mode="json")
    v2 = VoiceSessionOutcome.model_validate(data)
    assert v2.issue_type == IssueType.MECHANICAL_FAILURE
