"""Phase 2: POST (queue mode) → SQS → worker → Mongo; poison → DLQ.

Run: docker compose up -d && export $(grep -v '^#' .env | xargs) && \
  pytest -m integration tests/integration/test_phase2_sqs_pipeline.py -v
"""

import asyncio
import json
import os
import uuid
from typing import Any

import boto3
import pytest
from asgi_lifespan import LifespanManager
from httpx import ASGITransport, AsyncClient
from motor.motor_asyncio import AsyncIOMotorClient

from ais.app import create_app
from ais.config import Settings
from ais.sqs.client import SqsClient
from ais.worker.main import run_one_cycle


async def _mongo_reachable(uri: str) -> bool:
    client = AsyncIOMotorClient(uri, serverSelectionTimeoutMS=2500)
    try:
        await client.admin.command("ping")
        return True
    except Exception:
        return False
    finally:
        client.close()


def _sync_sqs_client(s: Settings) -> Any:
    return boto3.client(
        "sqs",
        endpoint_url=s.aws_endpoint_url,
        region_name=s.aws_region,
        aws_access_key_id=s.aws_access_key_id,
        aws_secret_access_key=s.aws_secret_access_key,
    )


@pytest.mark.integration
@pytest.mark.asyncio
async def test_queue_worker_persists_to_mongo() -> None:
    if os.getenv("SKIP_SQS_INTEGRATION"):
        pytest.skip("SKIP_SQS_INTEGRATION set")
    endpoint = os.getenv("AWS_ENDPOINT_URL")
    if not endpoint:
        pytest.skip("Set AWS_ENDPOINT_URL (e.g. http://localhost:4566)")

    base_uri = os.getenv("MONGO_URI", "mongodb://localhost:27017")
    mongo_uri = f"{base_uri}{'&' if '?' in base_uri else '?'}serverSelectionTimeoutMS=5000"
    if not await _mongo_reachable(mongo_uri):
        pytest.skip("Mongo not reachable")

    db_name = f"ais_sqs_{uuid.uuid4().hex[:12]}"
    settings = Settings(
        mongo_uri=mongo_uri,
        mongo_database=db_name,
        aws_endpoint_url=endpoint,
        aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID", "test"),
        aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY", "test"),
        aws_region=os.getenv("AWS_REGION", "eu-west-1"),
        queue_ingress=True,
        sqs_wait_time_seconds=1,
    )
    app = create_app(settings)
    sqs = SqsClient(settings)

    try:
        async with LifespanManager(app, startup_timeout=60):
            await sqs.ensure_queue_urls()
            transport = ASGITransport(app=app)
            payload = {
                "deliveryId": "D-sqs",
                "eventType": "location_update",
                "schemaVersion": 1,
                "payload": {"status": "from_queue"},
                "traceId": "sqs-trace-1",
            }
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                r = await client.post("/v1/events", json=payload)
                assert r.status_code == 200
                body = r.json()
                assert body["queued"] is True
                assert body["messageId"]

            for _ in range(30):
                n = await run_one_cycle(settings=settings, sqs=sqs, repo=app.state.event_repository)
                if n > 0:
                    break
                await asyncio.sleep(0.2)
            else:
                pytest.fail("worker did not receive a message within retries")

            async with AsyncClient(transport=transport, base_url="http://test") as client:
                g = await client.get("/v1/deliveries/D-sqs")
                assert g.status_code == 200
                assert len(g.json()["events"]) == 1

            mc = app.state.mongo_client
            db = mc[settings.mongo_database]
            assert await db.events.count_documents({}) == 1
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
async def test_invalid_ingress_body_lands_on_dlq_no_crash() -> None:
    if os.getenv("SKIP_SQS_INTEGRATION"):
        pytest.skip("SKIP_SQS_INTEGRATION set")
    endpoint = os.getenv("AWS_ENDPOINT_URL")
    if not endpoint:
        pytest.skip("Set AWS_ENDPOINT_URL")

    base_uri = os.getenv("MONGO_URI", "mongodb://localhost:27017")
    mongo_uri = f"{base_uri}{'&' if '?' in base_uri else '?'}serverSelectionTimeoutMS=5000"
    if not await _mongo_reachable(mongo_uri):
        pytest.skip("Mongo not reachable")

    db_name = f"ais_dlq_{uuid.uuid4().hex[:12]}"
    settings = Settings(
        mongo_uri=mongo_uri,
        mongo_database=db_name,
        aws_endpoint_url=endpoint,
        aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID", "test"),
        aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY", "test"),
        aws_region=os.getenv("AWS_REGION", "eu-west-1"),
        queue_ingress=True,
    )
    app = create_app(settings)
    sqs = SqsClient(settings)
    sync = _sync_sqs_client(settings)

    try:
        async with LifespanManager(app, startup_timeout=60):
            await sqs.ensure_queue_urls()
            for url in (sqs.ingress_queue_url, sqs.dlq_queue_url):
                try:
                    sync.purge_queue(QueueUrl=url)
                except Exception:
                    pass
            sync.send_message(
                QueueUrl=sqs.ingress_queue_url,
                MessageBody=json.dumps({"not": "an envelope"}),
            )
            n = await run_one_cycle(settings=settings, sqs=sqs, repo=app.state.event_repository)
            assert n == 1

            dlq = sync.receive_message(
                QueueUrl=sqs.dlq_queue_url,
                MaxNumberOfMessages=5,
                WaitTimeSeconds=2,
            )
            msgs = dlq.get("Messages") or []
            assert len(msgs) >= 1

            mc = app.state.mongo_client
            db = mc[settings.mongo_database]
            assert await db.events.count_documents({}) == 0
    finally:
        drop = AsyncIOMotorClient(mongo_uri, serverSelectionTimeoutMS=5000)
        try:
            await drop.drop_database(db_name)
        except Exception:
            pass
        finally:
            drop.close()
