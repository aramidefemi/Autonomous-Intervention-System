from datetime import datetime

from ais.models import Delivery, InterventionPlan, NormalizedEvent, WatchtowerDecision
from ais.repositories.contracts import EventRepository, IngestOutcome


class InMemoryEventRepository(EventRepository):
    """Unit-test double: same idempotency + delivery projection behavior as Mongo."""

    def __init__(self) -> None:
        self._events: dict[str, dict] = {}
        self._deliveries: dict[str, dict] = {}
        self._watchtower: list[dict] = []
        self._interventions: list[dict] = []

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

    async def append_watchtower_decision(self, decision: WatchtowerDecision) -> None:
        self._watchtower.append(
            {
                "delivery_id": decision.delivery_id,
                "risk": decision.risk.value,
                "reason": decision.reason,
                "signals": dict(decision.signals),
                "source": decision.source,
                "decided_at": decision.decided_at,
            }
        )

    async def list_watchtower_decisions(self, delivery_id: str, limit: int = 20) -> list[dict]:
        rows = [r for r in self._watchtower if r["delivery_id"] == delivery_id]
        rows.sort(key=lambda x: x["decided_at"], reverse=True)
        return rows[:limit]

    async def append_intervention_plan(self, plan: InterventionPlan) -> None:
        self._interventions.append(
            {
                "delivery_id": plan.delivery_id,
                "intervention_type": plan.intervention_type.value,
                "reason": plan.reason,
                "status": plan.status,
                "planned_at": plan.planned_at,
                "watchtower_risk": plan.watchtower_risk.value,
                "watchtower_reason": plan.watchtower_reason,
                "source": plan.source,
            }
        )

    async def last_intervention_planned_at(self, delivery_id: str) -> datetime | None:
        rows = [r for r in self._interventions if r["delivery_id"] == delivery_id]
        if not rows:
            return None
        rows.sort(key=lambda x: x["planned_at"], reverse=True)
        at = rows[0]["planned_at"]
        return at if isinstance(at, datetime) else None

    async def list_intervention_plans(self, delivery_id: str, limit: int = 20) -> list[dict]:
        rows = [r for r in self._interventions if r["delivery_id"] == delivery_id]
        rows.sort(key=lambda x: x["planned_at"], reverse=True)
        return rows[:limit]
