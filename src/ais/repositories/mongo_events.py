from datetime import UTC, datetime
from typing import Any

from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo.errors import DuplicateKeyError

from ais.models import (
    Delivery,
    InterventionPlan,
    NormalizedEvent,
    VoiceSessionOutcome,
    WatchtowerDecision,
)
from ais.recovery.checkpoint import delivery_has_stale_open_pipeline
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
    d: dict[str, Any] = {
        "delivery_id": decision.delivery_id,
        "risk": decision.risk.value,
        "reason": decision.reason,
        "signals": decision.signals,
        "source": decision.source,
        "decided_at": decision.decided_at,
    }
    if decision.ingest_idempotency_key:
        d["ingest_idempotency_key"] = decision.ingest_idempotency_key
    return d


def _intervention_doc(plan: InterventionPlan) -> dict[str, Any]:
    d: dict[str, Any] = {
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
    return d


def _voice_outcome_doc(outcome: VoiceSessionOutcome) -> dict[str, Any]:
    return {
        "delivery_id": outcome.delivery_id,
        "room_name": outcome.room_name,
        "transcript": outcome.transcript,
        "issue_type": outcome.issue_type.value,
        "structured": outcome.structured,
        "lifecycle": outcome.lifecycle,
        "source": outcome.source,
        "extraction_confidence": outcome.extraction_confidence,
        "extraction_method": outcome.extraction_method,
        "received_at": outcome.received_at,
    }


class MongoEventRepository(EventRepository):
    def __init__(self, db: AsyncIOMotorDatabase) -> None:
        self._db = db
        self._events = db["events"]
        self._deliveries = db["deliveries"]
        self._watchtower = db["watchtower_decisions"]
        self._interventions = db["interventions"]
        self._voice = db["voice_outcomes"]

    async def ensure_indexes(self) -> None:
        await self._events.create_index("idempotency_key", unique=True)
        await self._events.create_index("delivery_id")
        await self._deliveries.create_index("delivery_id", unique=True)
        await self._watchtower.create_index("delivery_id")
        await self._watchtower.create_index([("delivery_id", 1), ("decided_at", -1)])
        await self._watchtower.create_index(
            [("delivery_id", 1), ("ingest_idempotency_key", 1)],
            unique=True,
            partialFilterExpression={"ingest_idempotency_key": {"$type": "string"}},
        )
        await self._interventions.create_index("delivery_id")
        await self._interventions.create_index([("delivery_id", 1), ("planned_at", -1)])
        await self._interventions.create_index(
            [("delivery_id", 1), ("ingest_idempotency_key", 1)],
            unique=True,
            partialFilterExpression={"ingest_idempotency_key": {"$type": "string"}},
        )
        await self._voice.create_index("delivery_id")
        await self._voice.create_index([("delivery_id", 1), ("received_at", -1)])

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
            del_row = await self._deliveries.find_one(
                {"delivery_id": event.delivery_id},
                projection={"open_pipeline_idempotency_key": 1},
            )
            resume = (
                del_row is not None
                and del_row.get("open_pipeline_idempotency_key") == idempotency_key
            )
            return IngestOutcome(
                duplicate=True,
                trace_id=tid,
                delivery_id=event.delivery_id,
                idempotency_key=idempotency_key,
                resume_pipeline=resume,
            )

        upd = _delivery_update_from_event(event)
        started = datetime.now(UTC)
        await self._deliveries.update_one(
            {"delivery_id": event.delivery_id},
            {
                "$set": {
                    "status": upd["status"],
                    "last_updated_at": upd["last_updated_at"],
                    "metadata": upd["metadata"],
                    "open_pipeline_idempotency_key": idempotency_key,
                    "open_pipeline_started_at": started,
                },
                "$setOnInsert": {"delivery_id": event.delivery_id, "last_processed_seq": 0},
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
        try:
            await self._watchtower.insert_one(_watchtower_doc(decision))
        except DuplicateKeyError:
            if not decision.ingest_idempotency_key:
                raise

    async def get_watchtower_decision_for_ingest_key(
        self, delivery_id: str, ingest_idempotency_key: str
    ) -> WatchtowerDecision | None:
        row = await self._watchtower.find_one(
            {
                "delivery_id": delivery_id,
                "ingest_idempotency_key": ingest_idempotency_key,
            }
        )
        if not row:
            return None
        row.pop("_id", None)
        return WatchtowerDecision.model_validate(row)

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
        if plan.ingest_idempotency_key:
            dup = await self._interventions.find_one(
                {
                    "delivery_id": plan.delivery_id,
                    "ingest_idempotency_key": plan.ingest_idempotency_key,
                }
            )
            if dup is not None:
                return
        try:
            await self._interventions.insert_one(_intervention_doc(plan))
        except DuplicateKeyError:
            if not plan.ingest_idempotency_key:
                raise

    async def get_intervention_plan_for_ingest_key(
        self, delivery_id: str, ingest_idempotency_key: str
    ) -> InterventionPlan | None:
        row = await self._interventions.find_one(
            {
                "delivery_id": delivery_id,
                "ingest_idempotency_key": ingest_idempotency_key,
            }
        )
        if not row:
            return None
        row.pop("_id", None)
        return InterventionPlan.model_validate(row)

    async def complete_pipeline(self, delivery_id: str, idempotency_key: str) -> None:
        await self._deliveries.update_one(
            {
                "delivery_id": delivery_id,
                "open_pipeline_idempotency_key": idempotency_key,
            },
            {
                "$unset": {"open_pipeline_idempotency_key": "", "open_pipeline_started_at": ""},
                "$inc": {"last_processed_seq": 1},
            },
        )

    async def find_stale_open_pipeline_delivery_ids(
        self,
        *,
        stale_after_seconds: int,
        now: datetime | None = None,
    ) -> list[str]:
        t = now if now is not None else datetime.now(UTC)
        cur = self._deliveries.find(
            {"open_pipeline_idempotency_key": {"$exists": True, "$ne": None}},
            projection={
                "delivery_id": 1,
                "open_pipeline_idempotency_key": 1,
                "open_pipeline_started_at": 1,
            },
        )
        out: list[str] = []
        async for doc in cur:
            if not delivery_has_stale_open_pipeline(
                open_pipeline_idempotency_key=doc.get("open_pipeline_idempotency_key"),
                open_pipeline_started_at=doc.get("open_pipeline_started_at"),
                now=t,
                stale_after_seconds=stale_after_seconds,
            ):
                continue
            did = doc.get("delivery_id")
            if isinstance(did, str):
                out.append(did)
        return out

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

    async def append_voice_outcome(self, outcome: VoiceSessionOutcome) -> None:
        await self._voice.insert_one(_voice_outcome_doc(outcome))

    async def list_voice_outcomes(self, delivery_id: str, limit: int = 20) -> list[dict]:
        cur = (
            self._voice.find({"delivery_id": delivery_id}).sort("received_at", -1).limit(limit)
        )
        out: list[dict] = []
        async for doc in cur:
            doc.pop("_id", None)
            if isinstance(doc.get("received_at"), datetime):
                doc["received_at"] = doc["received_at"].isoformat()
            out.append(doc)
        return out
