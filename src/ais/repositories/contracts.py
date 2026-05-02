from dataclasses import dataclass

from ais.models import Delivery, NormalizedEvent, WatchtowerDecision


@dataclass(frozen=True)
class IngestOutcome:
    duplicate: bool
    trace_id: str
    delivery_id: str
    idempotency_key: str


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

    async def list_watchtower_decisions(self, delivery_id: str, limit: int = 20) -> list[dict]:
        raise NotImplementedError
