"""Phase 1 integration: POST /v1/events → Mongo; duplicate POST is deduped.

Run: docker compose up -d && pytest -m integration tests/integration/test_phase1_tracer.py -v
"""

import os
import uuid

import pytest
from asgi_lifespan import LifespanManager
from httpx import ASGITransport, AsyncClient
from motor.motor_asyncio import AsyncIOMotorClient

from ais.app import create_app
from ais.config import Settings


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
async def test_tracer_post_then_duplicate_no_extra_event() -> None:
    if os.getenv("SKIP_MONGO_INTEGRATION"):
        pytest.skip("SKIP_MONGO_INTEGRATION set")

    base_uri = os.getenv("MONGO_URI", "mongodb://localhost:27017")
    mongo_uri = f"{base_uri}{'&' if '?' in base_uri else '?'}serverSelectionTimeoutMS=5000"
    if not await _mongo_reachable(mongo_uri):
        pytest.skip("Mongo not reachable (start docker compose or set MONGO_URI)")

    db_name = f"ais_tracer_{uuid.uuid4().hex[:12]}"
    settings = Settings(
        mongo_uri=mongo_uri,
        mongo_database=db_name,
        aws_endpoint_url=None,
        queue_ingress=False,
    )
    app = create_app(settings)

    try:
        async with LifespanManager(app, startup_timeout=60):
            transport = ASGITransport(app=app)
            payload = {
                "deliveryId": "D-int",
                "eventType": "location_update",
                "schemaVersion": 1,
                "payload": {"status": "in_transit"},
                "traceId": "int-trace-1",
            }
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                r1 = await client.post("/v1/events", json=payload)
                r2 = await client.post("/v1/events", json=payload)
                assert r1.status_code == 200
                assert r2.status_code == 200
                assert r1.json()["duplicate"] is False
                assert r2.json()["duplicate"] is True
                g = await client.get("/v1/deliveries/D-int")
                assert g.status_code == 200
                assert len(g.json()["events"]) == 1

            mc = app.state.mongo_client
            db = mc[settings.mongo_database]
            assert await db.events.count_documents({}) == 1
            assert await db.deliveries.count_documents({"delivery_id": "D-int"}) == 1
    finally:
        drop = AsyncIOMotorClient(mongo_uri, serverSelectionTimeoutMS=5000)
        try:
            await drop.drop_database(db_name)
        except Exception:
            pass
        finally:
            drop.close()
