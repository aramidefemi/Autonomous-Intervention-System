from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field, model_validator

from ais.versioning import assert_supported_schema_version


class RiskLevel(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class Delivery(BaseModel):
    delivery_id: str = Field(..., min_length=1, alias="deliveryId")
    status: str = Field(default="unknown")
    last_updated_at: datetime | None = Field(default=None, alias="lastUpdatedAt")
    metadata: dict[str, Any] = Field(default_factory=dict)

    model_config = {"populate_by_name": True}


class NormalizedEvent(BaseModel):
    delivery_id: str = Field(..., min_length=1, alias="deliveryId")
    event_type: str = Field(..., min_length=1, alias="eventType")
    schema_version: int = Field(..., ge=1, alias="schemaVersion")
    occurred_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        alias="occurredAt",
    )
    payload: dict[str, Any] = Field(default_factory=dict)

    model_config = {"populate_by_name": True}

    @model_validator(mode="after")
    def supported_schema(self) -> "NormalizedEvent":
        assert_supported_schema_version(self.schema_version)
        return self


class AgentDecision(BaseModel):
    delivery_id: str = Field(..., min_length=1, alias="deliveryId")
    agent_name: str = Field(..., min_length=1, alias="agentName")
    summary: str = Field(default="")
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    decided_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        alias="decidedAt",
    )

    model_config = {"populate_by_name": True}


class WatchtowerDecision(BaseModel):
    """Rule- or LLM-backed health/risk assessment for a delivery (append-only history)."""

    delivery_id: str = Field(..., min_length=1, alias="deliveryId")
    risk: RiskLevel
    reason: str = Field(..., min_length=1)
    signals: dict[str, Any] = Field(default_factory=dict)
    source: str = Field(default="rules", description="rules | llm | ...")
    decided_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        alias="decidedAt",
    )

    model_config = {"populate_by_name": True}


class InterventionType(StrEnum):
    CALL_RIDER = "call_rider"
    CALL_CUSTOMER = "call_customer"
    WAIT = "wait"
    ESCALATE = "escalate"
    REASSIGN = "reassign"


class InterventionPlan(BaseModel):
    """Planner output: proposed next action for a delivery (append-only)."""

    delivery_id: str = Field(..., min_length=1, alias="deliveryId")
    intervention_type: InterventionType = Field(..., alias="interventionType")
    reason: str = Field(..., min_length=1)
    status: str = Field(default="pending")
    planned_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        alias="plannedAt",
    )
    watchtower_risk: RiskLevel = Field(..., alias="watchtowerRisk")
    watchtower_reason: str = Field(..., min_length=1, alias="watchtowerReason")
    source: str = Field(default="rules")

    model_config = {"populate_by_name": True}
