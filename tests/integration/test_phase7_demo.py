"""Phase 7: scripted demo path against real Mongo (optional)."""

import os
import uuid

import pytest
from asgi_lifespan import LifespanManager
from httpx import ASGITransport, AsyncClient
from motor.motor_asyncio import AsyncIOMotorClient

from ais.app import create_app
from ais.config import Settings
from ais.demo.scenario import run_bike_breakdown_demo


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
async def test_bike_breakdown_happy_path_mongo() -> None:
    if os.getenv("SKIP_MONGO_INTEGRATION"):
        pytest.skip("SKIP_MONGO_INTEGRATION set")

    base_uri = os.getenv("MONGO_URI", "mongodb://localhost:27017")
    mongo_uri = f"{base_uri}{'&' if '?' in base_uri else '?'}serverSelectionTimeoutMS=5000"
    if not await _mongo_reachable(mongo_uri):
        pytest.skip("Mongo not reachable")

    db_name = f"ais_ph7_{uuid.uuid4().hex[:12]}"
    settings = Settings(
        mongo_uri=mongo_uri,
        mongo_database=db_name,
        aws_endpoint_url=None,
        queue_ingress=False,
        intervention_cooldown_seconds=600,
    )
    app = create_app(settings)
    did = f"D-ph7-{uuid.uuid4().hex[:8]}"

    try:
        async with LifespanManager(app, startup_timeout=60):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                body = await run_bike_breakdown_demo(
                    base_url="http://test",
                    client=client,
                    delivery_id=did,
                )
        assert body["voiceOutcomes"]
        assert body["watchtowerDecisions"]
        assert body["interventionPlans"]
    finally:
        drop = AsyncIOMotorClient(mongo_uri, serverSelectionTimeoutMS=5000)
        try:
            await drop.drop_database(db_name)
        except Exception:
            pass
        finally:
            drop.close()
