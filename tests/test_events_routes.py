import pytest
from httpx import ASGITransport, AsyncClient


@pytest.mark.asyncio
async def test_post_event_accepted(app) -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.post(
            "/v1/events",
            json={
                "deliveryId": "D99",
                "eventType": "location_update",
                "schemaVersion": 1,
                "payload": {"status": "in_transit"},
            },
        )
        assert r.status_code == 200
        data = r.json()
        assert data["accepted"] is True
        assert data["duplicate"] is False
        assert data.get("queued") is False
        assert data["traceId"]
        assert data["deliveryId"] == "D99"
        g = await client.get("/v1/deliveries/D99")
        assert g.json()["watchtowerDecisions"]


@pytest.mark.asyncio
async def test_duplicate_post_same_body_no_second_side_effect(app) -> None:
    transport = ASGITransport(app=app)
    payload = {
        "deliveryId": "Ddup",
        "eventType": "ping",
        "schemaVersion": 1,
        "payload": {"status": "late"},
    }
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r1 = await client.post("/v1/events", json=payload)
        r2 = await client.post("/v1/events", json=payload)
        g = await client.get("/v1/deliveries/Ddup")
    assert r1.status_code == 200
    assert r2.status_code == 200
    assert r1.json()["duplicate"] is False
    assert r2.json()["duplicate"] is True
    assert r1.json()["traceId"] == r2.json()["traceId"]
    assert len(g.json()["events"]) == 1
    assert len(g.json()["watchtowerDecisions"]) == 1


@pytest.mark.asyncio
async def test_idempotency_header_duplicates_even_if_body_differs(app) -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r1 = await client.post(
            "/v1/events",
            headers={"Idempotency-Key": "fixed-key"},
            json={
                "deliveryId": "H1",
                "eventType": "a",
                "schemaVersion": 1,
                "payload": {"status": "x"},
            },
        )
        r2 = await client.post(
            "/v1/events",
            headers={"Idempotency-Key": "fixed-key"},
            json={
                "deliveryId": "H1",
                "eventType": "b",
                "schemaVersion": 1,
                "payload": {"status": "y"},
            },
        )
    assert r1.json()["duplicate"] is False
    assert r2.json()["duplicate"] is True


@pytest.mark.asyncio
async def test_get_delivery_404(app) -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.get("/v1/deliveries/missing")
    assert r.status_code == 404
