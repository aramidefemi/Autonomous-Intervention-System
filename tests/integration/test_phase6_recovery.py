"""Phase 6: seeded incomplete pipeline + duplicate ingress completes once."""

import os
import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest
from motor.motor_asyncio import AsyncIOMotorClient

from ais.ingest.ingress_envelope import envelope_to_json
from ais.repositories.mongo_events import MongoEventRepository
from ais.sqs.client import ReceivedMessage
from ais.worker.processing import process_ingress_message


async def _mongo_reachable(uri: str) -> bool:
    client = AsyncIOMotorClient(uri, serverSelectionTimeoutMS=2500)
    try:
        await client.admin.command("ping")
        return True
    except Exception:
        return False
    finally:
        client.close()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_resume_duplicate_completes_without_extra_intervention() -> None:
    if os.getenv("SKIP_MONGO_INTEGRATION"):
        pytest.skip("SKIP_MONGO_INTEGRATION set")

    base_uri = os.getenv("MONGO_URI", "mongodb://localhost:27017")
    mongo_uri = f"{base_uri}{'&' if '?' in base_uri else '?'}serverSelectionTimeoutMS=5000"
    if not await _mongo_reachable(mongo_uri):
        pytest.skip("Mongo not reachable")

    db_name = f"ais_ph6_{uuid.uuid4().hex[:12]}"
    mc = AsyncIOMotorClient(mongo_uri, serverSelectionTimeoutMS=8000)
    db = mc[db_name]
    repo = MongoEventRepository(db)
    await repo.ensure_indexes()

    now = datetime.now(UTC)
    old = now - timedelta(minutes=10)
    idem = "idem-ph6-int"
    delivery_id = "D-ph6-int"

    await db.events.insert_one(
        {
            "idempotency_key": idem,
            "trace_id": "tr6",
            "delivery_id": delivery_id,
            "event_type": "location_update",
            "schema_version": 1,
            "occurred_at": old,
            "payload": {"status": "in_transit"},
        }
    )
    await db.deliveries.insert_one(
        {
            "delivery_id": delivery_id,
            "status": "in_transit",
            "last_updated_at": old,
            "metadata": {"status": "in_transit"},
            "last_processed_seq": 0,
            "open_pipeline_idempotency_key": idem,
            "open_pipeline_started_at": now - timedelta(minutes=5),
        }
    )

    try:
        payload = {
            "deliveryId": delivery_id,
            "eventType": "location_update",
            "schemaVersion": 1,
            "occurredAt": old.isoformat(),
            "payload": {"status": "in_transit"},
        }
        body = envelope_to_json(payload, idem)
        sqs = MagicMock()
        sqs.ingress_queue_url = "u"
        sqs.delete_message = AsyncMock()
        msg = ReceivedMessage(body=body, receipt_handle="rh1", receive_count=1)
        await process_ingress_message(
            sqs=sqs,  # type: ignore[arg-type]
            repo=repo,
            msg=msg,
            max_receive_before_dlq=5,
            intervention_cooldown_seconds=3600,
        )
        n_w = await db.watchtower_decisions.count_documents({"delivery_id": delivery_id})
        n_i = await db.interventions.count_documents({"delivery_id": delivery_id})
        assert n_w >= 1
        assert n_i >= 1
        drow = await db.deliveries.find_one({"delivery_id": delivery_id})
        assert drow is not None
        assert drow.get("open_pipeline_idempotency_key") is None

        msg2 = ReceivedMessage(body=body, receipt_handle="rh2", receive_count=2)
        await process_ingress_message(
            sqs=sqs,  # type: ignore[arg-type]
            repo=repo,
            msg=msg2,
            max_receive_before_dlq=5,
            intervention_cooldown_seconds=3600,
        )
        assert await db.watchtower_decisions.count_documents({"delivery_id": delivery_id}) == n_w
        assert await db.interventions.count_documents({"delivery_id": delivery_id}) == n_i
    finally:
        try:
            await mc.drop_database(db_name)
        except Exception:
            pass
        finally:
            mc.close()
