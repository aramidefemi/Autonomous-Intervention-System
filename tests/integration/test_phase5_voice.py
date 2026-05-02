"""Phase 5: mock LiveKit-style callback → transcript + issue type in Mongo.

Run: pytest -m integration tests/integration/test_phase5_voice.py -v
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
async def test_voice_callback_contract_writes_mongo() -> None:
    if os.getenv("SKIP_MONGO_INTEGRATION"):
        pytest.skip("SKIP_MONGO_INTEGRATION set")

    base_uri = os.getenv("MONGO_URI", "mongodb://localhost:27017")
    mongo_uri = f"{base_uri}{'&' if '?' in base_uri else '?'}serverSelectionTimeoutMS=5000"
    if not await _mongo_reachable(mongo_uri):
        pytest.skip("Mongo not reachable")

    db_name = f"ais_voice_{uuid.uuid4().hex[:12]}"
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
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                await client.post(
                    "/v1/events",
                    json={
                        "deliveryId": "D-voice-int",
                        "eventType": "location_update",
                        "schemaVersion": 1,
                        "payload": {"status": "in_transit"},
                        "traceId": "v1",
                    },
                )
                r = await client.post(
                    "/v1/voice/callback",
                    json={
                        "deliveryId": "D-voice-int",
                        "roomName": "room_contract",
                        "transcript": "I'm stuck in traffic",
                        "sessionEvent": "session_ended",
                        "source": "mock_livekit",
                    },
                )
                assert r.status_code == 200
                assert r.json()["issueType"] == "traffic_delay"

            mc = app.state.mongo_client
            db = mc[settings.mongo_database]
            row = await db.voice_outcomes.find_one({"delivery_id": "D-voice-int"})
            assert row is not None
            assert row.get("issue_type") == "traffic_delay"
            assert "traffic" in (row.get("transcript") or "").lower()
    finally:
        drop = AsyncIOMotorClient(mongo_uri, serverSelectionTimeoutMS=5000)
        try:
            await drop.drop_database(db_name)
        except Exception:
            pass
        finally:
            drop.close()
