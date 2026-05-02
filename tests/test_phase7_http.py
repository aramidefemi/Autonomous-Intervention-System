import pytest
from httpx import ASGITransport, AsyncClient


@pytest.mark.asyncio
async def test_correlation_id_echo(app) -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.get("/health", headers={"X-Correlation-ID": "corr-phase7"})
    assert r.headers.get("X-Correlation-ID") == "corr-phase7"


@pytest.mark.asyncio
async def test_revision_conflict_on_stale_expected(app) -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        await client.post(
            "/v1/events",
            json={
                "deliveryId": "D-rev",
                "eventType": "ping",
                "schemaVersion": 1,
                "payload": {"status": "ok"},
            },
        )
        r = await client.post(
            "/v1/events",
            headers={"X-Expected-Delivery-Revision": "0"},
            json={
                "deliveryId": "D-rev",
                "eventType": "ping2",
                "schemaVersion": 1,
                "payload": {"status": "late"},
            },
        )
    assert r.status_code == 409
    body = r.json()
    assert body["detail"]["error"] == "revision_conflict"
    assert body["detail"]["currentRevision"] >= 1


@pytest.mark.asyncio
async def test_expected_revision_zero_first_write_ok(app) -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.post(
            "/v1/events",
            headers={"X-Expected-Delivery-Revision": "0"},
            json={
                "deliveryId": "D-new-rev",
                "eventType": "ping",
                "schemaVersion": 1,
                "payload": {"status": "ok"},
            },
        )
    assert r.status_code == 200
