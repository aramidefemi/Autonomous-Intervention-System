from datetime import UTC, datetime

from ais.models import (
    Delivery,
    InterventionPlan,
    NormalizedEvent,
    VoiceSessionOutcome,
    WatchtowerDecision,
)
from ais.recovery.checkpoint import delivery_has_stale_open_pipeline
from ais.repositories.contracts import EventRepository, IngestOutcome


class InMemoryEventRepository(EventRepository):
    """Unit-test double: same idempotency + delivery projection behavior as Mongo."""

    def __init__(self) -> None:
        self._events: dict[str, dict] = {}
        self._deliveries: dict[str, dict] = {}
        self._watchtower: list[dict] = []
        self._interventions: list[dict] = []
        self._voice: list[dict] = []

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
            row = self._deliveries.get(event.delivery_id)
            resume = row is not None and row.get("open_pipeline_idempotency_key") == idempotency_key
            return IngestOutcome(
                duplicate=True,
                trace_id=first["trace_id"],
                delivery_id=event.delivery_id,
                idempotency_key=idempotency_key,
                resume_pipeline=resume,
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
        started = datetime.now(UTC)
        prev = self._deliveries.get(event.delivery_id)
        seq = prev.get("last_processed_seq", 0) if prev else 0
        rev = (prev.get("revision", 0) if prev else 0) + 1
        self._deliveries[event.delivery_id] = {
            "delivery_id": event.delivery_id,
            "status": status,
            "last_updated_at": event.occurred_at,
            "metadata": event.payload,
            "last_processed_seq": seq,
            "revision": rev,
            "open_pipeline_idempotency_key": idempotency_key,
            "open_pipeline_started_at": started,
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
        d: dict = {
            "delivery_id": decision.delivery_id,
            "risk": decision.risk.value,
            "reason": decision.reason,
            "signals": dict(decision.signals),
            "source": decision.source,
            "decided_at": decision.decided_at,
        }
        if decision.ingest_idempotency_key:
            d["ingest_idempotency_key"] = decision.ingest_idempotency_key
        self._watchtower.append(d)

    async def get_watchtower_decision_for_ingest_key(
        self, delivery_id: str, ingest_idempotency_key: str
    ) -> WatchtowerDecision | None:
        for r in reversed(self._watchtower):
            if (
                r["delivery_id"] == delivery_id
                and r.get("ingest_idempotency_key") == ingest_idempotency_key
            ):
                return WatchtowerDecision.model_validate(r)
        return None

    async def list_watchtower_decisions(self, delivery_id: str, limit: int = 20) -> list[dict]:
        rows = [r for r in self._watchtower if r["delivery_id"] == delivery_id]
        rows.sort(key=lambda x: x["decided_at"], reverse=True)
        return rows[:limit]

    async def append_intervention_plan(self, plan: InterventionPlan) -> None:
        if plan.ingest_idempotency_key:
            if await self.get_intervention_plan_for_ingest_key(
                plan.delivery_id, plan.ingest_idempotency_key
            ):
                return
        d: dict = {
            "delivery_id": plan.delivery_id,
            "intervention_type": plan.intervention_type.value,
            "reason": plan.reason,
            "status": plan.status,
            "planned_at": plan.planned_at,
            "watchtower_risk": plan.watchtower_risk.value,
            "watchtower_reason": plan.watchtower_reason,
            "source": plan.source,
        }
        if plan.ingest_idempotency_key:
            d["ingest_idempotency_key"] = plan.ingest_idempotency_key
        self._interventions.append(d)

    async def get_intervention_plan_for_ingest_key(
        self, delivery_id: str, ingest_idempotency_key: str
    ) -> InterventionPlan | None:
        for r in reversed(self._interventions):
            if (
                r["delivery_id"] == delivery_id
                and r.get("ingest_idempotency_key") == ingest_idempotency_key
            ):
                return InterventionPlan.model_validate(r)
        return None

    async def complete_pipeline(self, delivery_id: str, idempotency_key: str) -> None:
        d = self._deliveries.get(delivery_id)
        if not d or d.get("open_pipeline_idempotency_key") != idempotency_key:
            return
        d["open_pipeline_idempotency_key"] = None
        d["open_pipeline_started_at"] = None
        d["last_processed_seq"] = d.get("last_processed_seq", 0) + 1
        d["revision"] = d.get("revision", 0) + 1

    async def find_stale_open_pipeline_delivery_ids(
        self,
        *,
        stale_after_seconds: int,
        now: datetime | None = None,
    ) -> list[str]:
        t = now if now is not None else datetime.now(UTC)
        out: list[str] = []
        for did, row in self._deliveries.items():
            if delivery_has_stale_open_pipeline(
                open_pipeline_idempotency_key=row.get("open_pipeline_idempotency_key"),
                open_pipeline_started_at=row.get("open_pipeline_started_at"),
                now=t,
                stale_after_seconds=stale_after_seconds,
            ):
                out.append(did)
        return out

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

    async def append_voice_outcome(self, outcome: VoiceSessionOutcome) -> None:
        row = self._deliveries.get(outcome.delivery_id)
        if row is not None:
            row["revision"] = row.get("revision", 0) + 1
        self._voice.append(
            {
                "delivery_id": outcome.delivery_id,
                "room_name": outcome.room_name,
                "transcript": outcome.transcript,
                "issue_type": outcome.issue_type.value,
                "structured": dict(outcome.structured),
                "lifecycle": outcome.lifecycle,
                "source": outcome.source,
                "extraction_confidence": outcome.extraction_confidence,
                "extraction_method": outcome.extraction_method,
                "received_at": outcome.received_at,
            }
        )

    async def list_voice_outcomes(self, delivery_id: str, limit: int = 20) -> list[dict]:
        rows = [r for r in self._voice if r["delivery_id"] == delivery_id]
        rows.sort(key=lambda x: x["received_at"], reverse=True)
        return rows[:limit]
