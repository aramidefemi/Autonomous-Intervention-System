from datetime import datetime
from typing import Any

from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo.errors import DuplicateKeyError

from ais.models import Delivery, NormalizedEvent
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


class MongoEventRepository(EventRepository):
    def __init__(self, db: AsyncIOMotorDatabase) -> None:
        self._db = db
        self._events = db["events"]
        self._deliveries = db["deliveries"]

    async def ensure_indexes(self) -> None:
        await self._events.create_index("idempotency_key", unique=True)
        await self._events.create_index("delivery_id")
        await self._deliveries.create_index("delivery_id", unique=True)

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
