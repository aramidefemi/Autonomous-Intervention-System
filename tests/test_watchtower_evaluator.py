import pytest

from ais.models import Delivery, NormalizedEvent, RiskLevel, WatchtowerDecision
from ais.watchtower.evaluator import RulesEvaluator
from ais.watchtower.service import run_watchtower
from ais.watchtower.signals import WatchtowerSignals
from tests.fakes import InMemoryEventRepository


class _StubLlmEvaluator:
    """Contract stand-in: tests can swap rules output without HTTP."""

    async def evaluate(
        self,
        *,
        delivery_id: str,
        delivery: Delivery,
        signals: WatchtowerSignals,
        events: list[dict],
    ) -> WatchtowerDecision:
        _ = delivery, signals, events
        return WatchtowerDecision(
            deliveryId=delivery_id,
            risk=RiskLevel.MEDIUM,
            reason="llm_override",
            signals={"stub": True},
            source="llm",
        )


@pytest.mark.asyncio
async def test_run_watchtower_with_custom_evaluator() -> None:
    repo = InMemoryEventRepository()
    await repo.ingest_event(
        idempotency_key="k1",
        event=NormalizedEvent(
            deliveryId="D-llm",
            eventType="ping",
            schemaVersion=1,
            payload={"status": "ok"},
        ),
        trace_id="t1",
    )
    await run_watchtower(repo, "D-llm", evaluator=_StubLlmEvaluator())
    rows = await repo.list_watchtower_decisions("D-llm")
    assert len(rows) == 1
    assert rows[0]["reason"] == "llm_override"
    assert rows[0]["source"] == "llm"


@pytest.mark.asyncio
async def test_rules_evaluator_delegates() -> None:
    ev = RulesEvaluator()
    d = Delivery(deliveryId="D1", status="s", lastUpdatedAt=None)
    sig = WatchtowerSignals(staleness_seconds=None, eta_delta_minutes=None)
    out = await ev.evaluate(
        delivery_id="D1",
        delivery=d,
        signals=sig,
        events=[],
    )
    assert out.reason == "nominal"
