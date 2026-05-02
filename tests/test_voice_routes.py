import pytest
from httpx import ASGITransport, AsyncClient


@pytest.mark.asyncio
async def test_voice_callback_404_without_delivery(app) -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.post(
            "/v1/voice/callback",
            json={
                "deliveryId": "missing",
                "roomName": "r1",
                "transcript": "hello",
            },
        )
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_voice_callback_persists_and_lists(app) -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        await client.post(
            "/v1/events",
            json={
                "deliveryId": "D-voice",
                "eventType": "ping",
                "schemaVersion": 1,
                "payload": {"status": "ok"},
            },
        )
        r = await client.post(
            "/v1/voice/callback",
            json={
                "deliveryId": "D-voice",
                "roomName": "room_x",
                "transcript": "My bike broke down",
                "sessionEvent": "session_ended",
            },
        )
        assert r.status_code == 200
        assert r.json()["issueType"] == "mechanical_failure"
        g = await client.get("/v1/deliveries/D-voice")
        vo = g.json()["voiceOutcomes"]
        assert len(vo) == 1
        assert vo[0]["issue_type"] == "mechanical_failure"
        assert "broke down" in vo[0]["transcript"]
