import pytest
from httpx import ASGITransport, AsyncClient


@pytest.mark.asyncio
async def test_health_ok(app) -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}
