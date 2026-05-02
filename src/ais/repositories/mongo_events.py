from datetime import datetime
from typing import Any

from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo.errors import DuplicateKeyError

from ais.models import Delivery, InterventionPlan, NormalizedEvent, WatchtowerDecision
from ais.repositories.contracts import EventRepository, IngestOutcome


def _event_doc(
    *,
    idempotency_key: str,
    event: NormalizedEvent,
    trace_id: str,
) -> dict[str, Any]:
    return {
        "idempotency_key": idempotency_key,
        "trace_id": trace_id,
        "delivery_id": event.delivery_id,
        "event_type": event.event_type,
        "schema_version": event.schema_version,
        "occurred_at": event.occurred_at,
        "payload": event.payload,
    }


def _delivery_update_from_event(event: NormalizedEvent) -> dict[str, Any]:
    status = event.payload.get("status")
    if not isinstance(status, str) or not status:
        status = "unknown"
    return {
        "delivery_id": event.delivery_id,
        "status": status,
        "last_updated_at": event.occurred_at,
        "metadata": event.payload,
    }


def _watchtower_doc(decision: WatchtowerDecision) -> dict[str, Any]:
    return {
        "delivery_id": decision.delivery_id,
        "risk": decision.risk.value,
        "reason": decision.reason,
        "signals": decision.signals,
        "source": decision.source,
        "decided_at": decision.decided_at,
    }


def _intervention_doc(plan: InterventionPlan) -> dict[str, Any]:
    return {
        "delivery_id": plan.delivery_id,
        "intervention_type": plan.intervention_type.value,
        "reason": plan.reason,
        "status": plan.status,
        "planned_at": plan.planned_at,
        "watchtower_risk": plan.watchtower_risk.value,
        "watchtower_reason": plan.watchtower_reason,
        "source": plan.source,
    }


class MongoEventRepository(EventRepository):
    def __init__(self, db: AsyncIOMotorDatabase) -> None:
        self._db = db
        self._events = db["events"]
        self._deliveries = db["deliveries"]
        self._watchtower = db["watchtower_decisions"]
        self._interventions = db["interventions"]

    async def ensure_indexes(self) -> None:
        await self._events.create_index("idempotency_key", unique=True)
        await self._events.create_index("delivery_id")
        await self._deliveries.create_index("delivery_id", unique=True)
        await self._watchtower.create_index("delivery_id")
        await self._watchtower.create_index([("delivery_id", 1), ("decided_at", -1)])
        await self._interventions.create_index("delivery_id")
        await self._interventions.create_index([("delivery_id", 1), ("planned_at", -1)])

    async def ingest_event(
        self,
        *,
        idempotency_key: str,
        event: NormalizedEvent,
        trace_id: str,
    ) -> IngestOutcome:
        doc = _event_doc(
            idempotency_key=idempotency_key,
            event=event,
            trace_id=trace_id,
        )
        try:
            await self._events.insert_one(doc)
        except DuplicateKeyError:
            existing = await self._events.find_one(
                {"idempotency_key": idempotency_key},
                projection={"trace_id": 1},
            )
            tid = (existing or {}).get("trace_id") or trace_id
            return IngestOutcome(
                duplicate=True,
                trace_id=tid,
                delivery_id=event.delivery_id,
                idempotency_key=idempotency_key,
            )

        upd = _delivery_update_from_event(event)
        await self._deliveries.update_one(
            {"delivery_id": event.delivery_id},
            {
                "$set": {
                    "status": upd["status"],
                    "last_updated_at": upd["last_updated_at"],
                    "metadata": upd["metadata"],
                },
                "$setOnInsert": {"delivery_id": event.delivery_id},
            },
            upsert=True,
        )
        return IngestOutcome(
            duplicate=False,
            trace_id=trace_id,
            delivery_id=event.delivery_id,
            idempotency_key=idempotency_key,
        )

    async def get_delivery(self, delivery_id: str) -> Delivery | None:
        row = await self._deliveries.find_one({"delivery_id": delivery_id})
        if not row:
            return None
        row.pop("_id", None)
        return Delivery.model_validate(row)

    async def list_events_for_delivery(self, delivery_id: str, limit: int = 50) -> list[dict]:
        cur = self._events.find({"delivery_id": delivery_id}).sort("occurred_at", 1).limit(limit)
        out: list[dict] = []
        async for doc in cur:
            doc.pop("_id", None)
            if isinstance(doc.get("occurred_at"), datetime):
                doc["occurred_at"] = doc["occurred_at"].isoformat()
            out.append(doc)
        return out

    async def append_watchtower_decision(self, decision: WatchtowerDecision) -> None:
        await self._watchtower.insert_one(_watchtower_doc(decision))

    async def list_watchtower_decisions(self, delivery_id: str, limit: int = 20) -> list[dict]:
        cur = (
            self._watchtower.find({"delivery_id": delivery_id}).sort("decided_at", -1).limit(limit)
        )
        out: list[dict] = []
        async for doc in cur:
            doc.pop("_id", None)
            if isinstance(doc.get("decided_at"), datetime):
                doc["decided_at"] = doc["decided_at"].isoformat()
            out.append(doc)
        return out

    async def append_intervention_plan(self, plan: InterventionPlan) -> None:
        await self._interventions.insert_one(_intervention_doc(plan))

    async def last_intervention_planned_at(self, delivery_id: str) -> datetime | None:
        doc = await self._interventions.find_one(
            {"delivery_id": delivery_id},
            sort=[("planned_at", -1)],
            projection={"planned_at": 1},
        )
        if not doc:
            return None
        at = doc.get("planned_at")
        return at if isinstance(at, datetime) else None

    async def list_intervention_plans(self, delivery_id: str, limit: int = 20) -> list[dict]:
        cur = (
            self._interventions.find({"delivery_id": delivery_id})
            .sort("planned_at", -1)
            .limit(limit)
        )
        out: list[dict] = []
        async for doc in cur:
            doc.pop("_id", None)
            if isinstance(doc.get("planned_at"), datetime):
                doc["planned_at"] = doc["planned_at"].isoformat()
            out.append(doc)
        return out
