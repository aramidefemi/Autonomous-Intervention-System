"""Load state → signals → evaluate → persist."""

from datetime import UTC, datetime

from ais.models import WatchtowerDecision
from ais.repositories import EventRepository
from ais.watchtower.evaluator import RulesEvaluator, WatchtowerEvaluator
from ais.watchtower.signals import compute_signals


async def run_watchtower(
    repo: EventRepository,
    delivery_id: str,
    *,
    now: datetime | None = None,
    evaluator: WatchtowerEvaluator | None = None,
    ingest_idempotency_key: str | None = None,
) -> WatchtowerDecision | None:
    t = now if now is not None else datetime.now(UTC)
    if ingest_idempotency_key:
        existing = await repo.get_watchtower_decision_for_ingest_key(
            delivery_id, ingest_idempotency_key
        )
        if existing is not None:
            return existing
    delivery = await repo.get_delivery(delivery_id)
    if delivery is None:
        return None
    events = await repo.list_events_for_delivery(delivery_id)
    signals = compute_signals(delivery, events, now=t)
    ev = evaluator or RulesEvaluator()
    decision = await ev.evaluate(
        delivery_id=delivery_id,
        delivery=delivery,
        signals=signals,
        events=events,
    )
    if ingest_idempotency_key:
        decision = decision.model_copy(
            update={"ingest_idempotency_key": ingest_idempotency_key}
        )
    await repo.append_watchtower_decision(decision)
    return decision
