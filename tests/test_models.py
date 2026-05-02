import json
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from ais.models import AgentDecision, Delivery, NormalizedEvent


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
