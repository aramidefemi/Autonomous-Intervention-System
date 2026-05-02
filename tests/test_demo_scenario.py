import pytest
from httpx import ASGITransport, AsyncClient

from ais.demo.scenario import bike_breakdown_payloads, run_bike_breakdown_demo


def test_bike_breakdown_payloads_have_delivery_id() -> None:
    did = "D-custom"
    for p in bike_breakdown_payloads(did):
        assert p["deliveryId"] == did
        assert p["schemaVersion"] == 1


@pytest.mark.asyncio
async def test_demo_scenario_end_to_end(app) -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        body = await run_bike_breakdown_demo(
            base_url="http://test",
            client=client,
            delivery_id="D-demo-unit",
        )
    assert body["voiceOutcomes"]
    assert body["voiceOutcomes"][0]["issue_type"] == "mechanical_failure"
    assert body["watchtowerDecisions"]
    assert body["interventionPlans"]
