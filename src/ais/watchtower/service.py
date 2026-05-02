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
) -> WatchtowerDecision | None:
    t = now if now is not None else datetime.now(UTC)
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
    await repo.append_watchtower_decision(decision)
    return decision
