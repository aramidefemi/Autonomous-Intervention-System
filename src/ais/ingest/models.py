from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator

from ais.models import NormalizedEvent
from ais.versioning import assert_supported_schema_version


class IngestPayload(BaseModel):
    delivery_id: str = Field(..., min_length=1, alias="deliveryId")
    event_type: str = Field(..., min_length=1, alias="eventType")
    schema_version: int = Field(..., ge=1, alias="schemaVersion")
    occurred_at: datetime | None = Field(default=None, alias="occurredAt")
    payload: dict[str, Any] = Field(default_factory=dict)
    trace_id: str | None = Field(default=None, alias="traceId")

    model_config = {"populate_by_name": True}

    @field_validator("schema_version")
    @classmethod
    def supported_schema(cls, v: int) -> int:
        assert_supported_schema_version(v)
        return v


def payload_to_normalized(p: IngestPayload) -> tuple[NormalizedEvent, str]:
    """Returns normalized event and trace id (payload trace or caller must generate)."""
    occurred = p.occurred_at or datetime.now(UTC)
    trace = (p.trace_id or "").strip() or None
    ev = NormalizedEvent(
        deliveryId=p.delivery_id,
        eventType=p.event_type,
        schemaVersion=p.schema_version,
        occurredAt=occurred,
        payload=p.payload,
    )
    return ev, trace
