from ais.models import Delivery, NormalizedEvent
from ais.repositories.contracts import EventRepository, IngestOutcome


class InMemoryEventRepository(EventRepository):
    """Unit-test double: same idempotency + delivery projection behavior as Mongo."""

    def __init__(self) -> None:
        self._events: dict[str, dict] = {}
        self._deliveries: dict[str, dict] = {}

    async def ensure_indexes(self) -> None:
        return

    async def ingest_event(
        self,
        *,
        idempotency_key: str,
        event: NormalizedEvent,
        trace_id: str,
    ) -> IngestOutcome:
        if idempotency_key in self._events:
            first = self._events[idempotency_key]
            return IngestOutcome(
                duplicate=True,
                trace_id=first["trace_id"],
                delivery_id=event.delivery_id,
                idempotency_key=idempotency_key,
            )

        self._events[idempotency_key] = {
            "idempotency_key": idempotency_key,
            "trace_id": trace_id,
            "delivery_id": event.delivery_id,
            "event_type": event.event_type,
            "schema_version": event.schema_version,
            "occurred_at": event.occurred_at,
            "payload": event.payload,
        }
        status = event.payload.get("status")
        if not isinstance(status, str) or not status:
            status = "unknown"
        self._deliveries[event.delivery_id] = {
            "delivery_id": event.delivery_id,
            "status": status,
            "last_updated_at": event.occurred_at,
            "metadata": event.payload,
        }
        return IngestOutcome(
            duplicate=False,
            trace_id=trace_id,
            delivery_id=event.delivery_id,
            idempotency_key=idempotency_key,
        )

    async def get_delivery(self, delivery_id: str) -> Delivery | None:
        row = self._deliveries.get(delivery_id)
        if not row:
            return None
        return Delivery.model_validate(row)

    async def list_events_for_delivery(self, delivery_id: str, limit: int = 50) -> list[dict]:
        rows = [e for e in self._events.values() if e["delivery_id"] == delivery_id]
        rows.sort(key=lambda x: x["occurred_at"])
        return rows[:limit]
