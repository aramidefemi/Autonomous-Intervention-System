"""LangGraph watchtower: parity with legacy evaluator + trace shape."""

from datetime import UTC, datetime

import pytest

from ais.models import Delivery, NormalizedEvent, RiskLevel, WatchtowerAction, WatchtowerDecision
from ais.watchtower.evaluator import RulesEvaluator
from ais.watchtower.graph import run_watchtower_graph
from ais.watchtower.rules import decide_from_rules
from ais.watchtower.service import run_watchtower
from ais.watchtower.signals import WatchtowerSignals
from tests.fakes import InMemoryEventRepository


def _signals_nominal() -> WatchtowerSignals:
    return WatchtowerSignals(
        staleness_seconds=10.0,
        eta_delta_minutes=None,
    )


@pytest.mark.asyncio
async def test_graph_matches_rules_evaluator_nominal() -> None:
    repo = InMemoryEventRepository()
    await repo.ingest_event(
        idempotency_key="gk1",
        event=NormalizedEvent(
            deliveryId="G1",
            eventType="ping",
            schemaVersion=1,
            payload={"status": "ok"},
        ),
        trace_id="t1",
    )
    sig = _signals_nominal()
    delivery = await repo.get_delivery("G1")
    assert delivery is not None
    direct = await RulesEvaluator().evaluate(
        delivery_id="G1",
        delivery=delivery,
        signals=sig,
        events=[],
    )
    graph_d = await run_watchtower_graph(
        delivery_id="G1",
        delivery=delivery,
        signals=sig,
        events=[],
        evaluator=RulesEvaluator(),
        ingest_idempotency_key=None,
    )
    assert graph_d.risk == direct.risk
    assert graph_d.reason == direct.reason
    assert graph_d.action == direct.action
    assert graph_d.signals == direct.signals
    assert graph_d.source == direct.source
    assert graph_d.graph_trace is not None
    assert graph_d.graph_trace.graph_name == "watchtower"
    assert any(s.node_name == "rules_gate" for s in graph_d.graph_trace.steps)
    assert graph_d.graph_trace.route_taken


@pytest.mark.asyncio
async def test_run_watchtower_graph_flag_adds_trace() -> None:
    repo = InMemoryEventRepository()
    await repo.ingest_event(
        idempotency_key="gk2",
        event=NormalizedEvent(
            deliveryId="G2",
            eventType="ping",
            schemaVersion=1,
            payload={"status": "ok"},
        ),
        trace_id="t1",
    )
    d1 = await run_watchtower(
        repo,
        "G2",
        use_watchtower_graph=True,
    )
    assert d1 is not None
    assert d1.graph_trace is not None
    d2 = await run_watchtower(
        repo,
        "G2",
        use_watchtower_graph=False,
    )
    assert d2 is not None
    assert d2.graph_trace is None


@pytest.mark.asyncio
async def test_stale_path_includes_llm_nodes_when_nvidia_route(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Non-nominal + nvidia kind → compressor + synthesizer; source becomes langgraph after LLM."""

    class LlmStub:
        async def evaluate(self, **kwargs):  # type: ignore[no-untyped-def]
            return WatchtowerDecision(
                deliveryId=kwargs["delivery_id"],
                risk=RiskLevel.HIGH,
                reason="stub",
                action=WatchtowerAction.ESCALATE,
                signals={},
                source="llm",
            )

    import ais.watchtower.graph as graph_mod

    monkeypatch.setattr(graph_mod, "_evaluator_kind", lambda _ev: "nvidia")

    sig = WatchtowerSignals(staleness_seconds=400.0, eta_delta_minutes=None)
    deliv = Delivery(deliveryId="G3", status="x", lastUpdatedAt=datetime.now(UTC))
    d = await run_watchtower_graph(
        delivery_id="G3",
        delivery=deliv,
        signals=sig,
        events=[{"eventType": "location", "payload": {}}],
        evaluator=LlmStub(),  # type: ignore[arg-type]
        ingest_idempotency_key="k1",
    )
    assert d.source == "langgraph"
    assert d.graph_trace is not None
    names = [s.node_name for s in d.graph_trace.steps]
    assert "signal_compressor" in names
    assert "risk_synthesizer" in names


@pytest.mark.asyncio
async def test_rules_stale_same_as_decide_from_rules() -> None:
    sig = WatchtowerSignals(staleness_seconds=999.0, eta_delta_minutes=None)
    deliv = Delivery(deliveryId="G4", status="x", lastUpdatedAt=datetime.now(UTC))
    expected = decide_from_rules(sig, delivery_id="G4")
    got = await run_watchtower_graph(
        delivery_id="G4",
        delivery=deliv,
        signals=sig,
        events=[],
        evaluator=RulesEvaluator(),
        ingest_idempotency_key=None,
    )
    assert got.risk == expected.risk
    assert got.reason == expected.reason
    assert got.source == "rules"
