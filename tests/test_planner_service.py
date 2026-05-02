"""Planner service + repo."""

from datetime import UTC, datetime, timedelta

import pytest

from ais.models import InterventionType, NormalizedEvent, RiskLevel, WatchtowerDecision
from ais.planner import run_intervention_planner
from tests.fakes import InMemoryEventRepository


@pytest.mark.asyncio
async def test_persists_when_not_in_cooldown() -> None:
    repo = InMemoryEventRepository()
    await repo.ingest_event(
        idempotency_key="a",
        event=NormalizedEvent(
            deliveryId="D1",
            eventType="x",
            schemaVersion=1,
            payload={"status": "x"},
        ),
        trace_id="t",
    )
    dec = WatchtowerDecision(
        deliveryId="D1",
        risk=RiskLevel.HIGH,
        reason="stale_update",
        signals={},
    )
    t = datetime(2026, 5, 2, 12, 0, 0, tzinfo=UTC)
    out = await run_intervention_planner(repo, dec, now=t, cooldown_seconds=60)
    assert out is not None
    assert out.intervention_type == InterventionType.CALL_RIDER
    rows = await repo.list_intervention_plans("D1")
    assert len(rows) == 1


@pytest.mark.asyncio
async def test_skips_when_cooldown() -> None:
    repo = InMemoryEventRepository()
    ev = NormalizedEvent(
        deliveryId="D2",
        eventType="x",
        schemaVersion=1,
        payload={"status": "x"},
    )
    await repo.ingest_event(idempotency_key="a", event=ev, trace_id="t")
    dec = WatchtowerDecision(
        deliveryId="D2",
        risk=RiskLevel.HIGH,
        reason="stale_update",
        signals={},
    )
    t0 = datetime(2026, 5, 2, 12, 0, 0, tzinfo=UTC)
    await run_intervention_planner(repo, dec, now=t0, cooldown_seconds=300)
    t1 = t0 + timedelta(seconds=30)
    out2 = await run_intervention_planner(repo, dec, now=t1, cooldown_seconds=300)
    assert out2 is None
    assert len(await repo.list_intervention_plans("D2")) == 1
