import pytest
from httpx import ASGITransport, AsyncClient

@pytest.mark.asyncio
async def test_voice_simulate_session_503_without_livekit(app) -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        await client.post(
            "/v1/events",
            json={
                "deliveryId": "D-sim",
                "eventType": "ping",
                "schemaVersion": 1,
                "payload": {"status": "ok"},
            },
        )
        r = await client.post("/v1/voice/simulate/session", json={"deliveryId": "D-sim"})
    assert r.status_code == 503


@pytest.mark.asyncio
async def test_voice_simulate_flow(app_livekit) -> None:
    transport = ASGITransport(app=app_livekit)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        await client.post(
            "/v1/events",
            json={
                "deliveryId": "D-sim",
                "eventType": "ping",
                "schemaVersion": 1,
                "payload": {"status": "ok"},
            },
        )
        r = await client.post("/v1/voice/simulate/session", json={"deliveryId": "D-sim"})
        assert r.status_code == 200
        body = r.json()
        assert body["livekitUrl"] == "wss://example.livekit.cloud"
        assert body["roomName"].startswith("wt-D-sim-")
        assert len(body["token"]) > 40
        assert body["identity"] == "sim-D-sim"
        assert "/v1/voice/simulate/ui/D-sim" in body["joinPageUrl"]
        assert "openingLine" in body
        assert body["openingSource"] in ("llm", "rules")
        assert "D-sim" in body["openingLine"]

        u = await client.get("/v1/voice/simulate/ui/D-sim")
        assert u.status_code == 200
        assert "livekit-client" in u.text


@pytest.mark.asyncio
async def test_voice_simulate_opening_no_livekit_ok(app) -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        await client.post(
            "/v1/events",
            json={
                "deliveryId": "D-open",
                "eventType": "ping",
                "schemaVersion": 1,
                "payload": {"status": "ok"},
            },
        )
        r = await client.get("/v1/voice/simulate/opening/D-open")
    assert r.status_code == 200
    j = r.json()
    assert j["openingSource"] in ("llm", "rules")
    assert "D-open" in j["openingLine"]


@pytest.mark.asyncio
async def test_voice_tts_503_without_elevenlabs(app) -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.post("/v1/voice/tts", json={"text": "Hello there"})
    assert r.status_code == 503


@pytest.mark.asyncio
async def test_voice_simulate_session_404_unknown_delivery(app_livekit) -> None:
    transport = ASGITransport(app_livekit)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.post("/v1/voice/simulate/session", json={"deliveryId": "missing"})
    assert r.status_code == 404
