"""Phase 4: watchtower → intervention plan in Mongo; cooldown blocks duplicate plans.

Run with Mongo up: pytest -m integration tests/integration/test_phase4_intervention_planner.py -v
"""

import os
import uuid
from datetime import UTC, datetime, timedelta

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
async def test_stale_event_yields_call_rider_plan() -> None:
    if os.getenv("SKIP_MONGO_INTEGRATION"):
        pytest.skip("SKIP_MONGO_INTEGRATION set")

    base_uri = os.getenv("MONGO_URI", "mongodb://localhost:27017")
    mongo_uri = f"{base_uri}{'&' if '?' in base_uri else '?'}serverSelectionTimeoutMS=5000"
    if not await _mongo_reachable(mongo_uri):
        pytest.skip("Mongo not reachable")

    db_name = f"ais_pl_{uuid.uuid4().hex[:12]}"
    settings = Settings(
        mongo_uri=mongo_uri,
        mongo_database=db_name,
        aws_endpoint_url=None,
        queue_ingress=False,
        intervention_cooldown_seconds=600,
        nvidia_api_key=None,  # rules-only; .env key would use LLM (non-deterministic)
    )
    app = create_app(settings)

    try:
        async with LifespanManager(app, startup_timeout=60):
            transport = ASGITransport(app=app)
            old = (datetime.now(UTC) - timedelta(minutes=10)).isoformat()
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                r = await client.post(
                    "/v1/events",
                    json={
                        "deliveryId": "D-pl-int",
                        "eventType": "location_update",
                        "schemaVersion": 1,
                        "occurredAt": old,
                        "payload": {"status": "in_transit"},
                        "traceId": "pl-1",
                    },
                )
                assert r.status_code == 200
                g = await client.get("/v1/deliveries/D-pl-int")
                assert g.status_code == 200
                body = g.json()
                assert len(body["interventionPlans"]) >= 1
                latest = body["interventionPlans"][0]
                assert latest["intervention_type"] == "call_rider"
                assert latest["watchtower_risk"] == "high"

            mc = app.state.mongo_client
            db = mc[settings.mongo_database]
            assert await db.interventions.count_documents({"delivery_id": "D-pl-int"}) >= 1
    finally:
        drop = AsyncIOMotorClient(mongo_uri, serverSelectionTimeoutMS=5000)
        try:
            await drop.drop_database(db_name)
        except Exception:
            pass
        finally:
            drop.close()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_second_tick_same_delivery_respects_cooldown() -> None:
    if os.getenv("SKIP_MONGO_INTEGRATION"):
        pytest.skip("SKIP_MONGO_INTEGRATION set")

    base_uri = os.getenv("MONGO_URI", "mongodb://localhost:27017")
    mongo_uri = f"{base_uri}{'&' if '?' in base_uri else '?'}serverSelectionTimeoutMS=5000"
    if not await _mongo_reachable(mongo_uri):
        pytest.skip("Mongo not reachable")

    db_name = f"ais_pl_cd_{uuid.uuid4().hex[:12]}"
    settings = Settings(
        mongo_uri=mongo_uri,
        mongo_database=db_name,
        aws_endpoint_url=None,
        queue_ingress=False,
        intervention_cooldown_seconds=3600,
        nvidia_api_key=None,
    )
    app = create_app(settings)

    try:
        async with LifespanManager(app, startup_timeout=60):
            transport = ASGITransport(app=app)
            old = (datetime.now(UTC) - timedelta(minutes=10)).isoformat()
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                p1 = {
                    "deliveryId": "D-pl-cd",
                    "eventType": "location_update",
                    "schemaVersion": 1,
                    "occurredAt": old,
                    "payload": {"status": "in_transit"},
                    "traceId": "cd-1",
                }
                p2 = {**p1, "traceId": "cd-2"}
                r1 = await client.post("/v1/events", json=p1)
                r2 = await client.post("/v1/events", json=p2)
                assert r1.status_code == 200
                assert r2.status_code == 200
                g = await client.get("/v1/deliveries/D-pl-cd")
                assert len(g.json()["interventionPlans"]) == 1
    finally:
        drop = AsyncIOMotorClient(mongo_uri, serverSelectionTimeoutMS=5000)
        try:
            await drop.drop_database(db_name)
        except Exception:
            pass
        finally:
            drop.close()
