from dataclasses import dataclass
from datetime import datetime

from ais.models import (
    Delivery,
    InterventionPlan,
    NormalizedEvent,
    VoiceSessionOutcome,
    WatchtowerDecision,
)


@dataclass(frozen=True)
class IngestOutcome:
    duplicate: bool
    trace_id: str
    delivery_id: str
    idempotency_key: str
    resume_pipeline: bool = False


class EventRepository:
    async def ensure_indexes(self) -> None:
        raise NotImplementedError

    async def ingest_event(
        self,
        *,
        idempotency_key: str,
        event: NormalizedEvent,
        trace_id: str,
    ) -> IngestOutcome:
        raise NotImplementedError

    async def get_delivery(self, delivery_id: str) -> Delivery | None:
        raise NotImplementedError

    async def list_events_for_delivery(self, delivery_id: str, limit: int = 50) -> list[dict]:
        raise NotImplementedError

    async def append_watchtower_decision(self, decision: WatchtowerDecision) -> None:
        raise NotImplementedError

    async def get_watchtower_decision_for_ingest_key(
        self, delivery_id: str, ingest_idempotency_key: str
    ) -> WatchtowerDecision | None:
        raise NotImplementedError

    async def list_watchtower_decisions(self, delivery_id: str, limit: int = 20) -> list[dict]:
        raise NotImplementedError

    async def append_intervention_plan(self, plan: InterventionPlan) -> None:
        raise NotImplementedError

    async def get_intervention_plan_for_ingest_key(
        self, delivery_id: str, ingest_idempotency_key: str
    ) -> InterventionPlan | None:
        raise NotImplementedError

    async def complete_pipeline(self, delivery_id: str, idempotency_key: str) -> None:
        raise NotImplementedError

    async def find_stale_open_pipeline_delivery_ids(
        self,
        *,
        stale_after_seconds: int,
        now: datetime | None = None,
    ) -> list[str]:
        raise NotImplementedError

    async def last_intervention_planned_at(self, delivery_id: str) -> datetime | None:
        raise NotImplementedError

    async def list_intervention_plans(self, delivery_id: str, limit: int = 20) -> list[dict]:
        raise NotImplementedError

    async def append_voice_outcome(self, outcome: VoiceSessionOutcome) -> None:
        raise NotImplementedError

    async def list_voice_outcomes(self, delivery_id: str, limit: int = 20) -> list[dict]:
        raise NotImplementedError

    async def list_delivery_summaries(self, limit: int = 100) -> list[dict]:
        """Sidebar index: each row has deliveryId, status, lastUpdatedAt (ISO string or omitted)."""
        raise NotImplementedError
