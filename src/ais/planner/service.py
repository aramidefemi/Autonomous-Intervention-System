"""Persist intervention plan after watchtower when not in cooldown."""

from datetime import UTC, datetime

from ais.models import InterventionPlan, WatchtowerDecision
from ais.planner.cooldown import is_within_cooldown
from ais.planner.policy import intervention_plan_from_decision
from ais.repositories import EventRepository


async def run_intervention_planner(
    repo: EventRepository,
    decision: WatchtowerDecision,
    *,
    now: datetime | None = None,
    cooldown_seconds: int = 300,
    ingest_idempotency_key: str | None = None,
) -> InterventionPlan | None:
    t = now if now is not None else datetime.now(UTC)
    if ingest_idempotency_key:
        existing_plan = await repo.get_intervention_plan_for_ingest_key(
            decision.delivery_id, ingest_idempotency_key
        )
        if existing_plan is not None:
            return existing_plan
    candidate = intervention_plan_from_decision(decision, planned_at=t)
    if candidate is None:
        return None
    if ingest_idempotency_key:
        candidate = candidate.model_copy(
            update={"ingest_idempotency_key": ingest_idempotency_key}
        )
    last_at = await repo.last_intervention_planned_at(decision.delivery_id)
    if is_within_cooldown(t, last_at, cooldown_seconds):
        return None
    await repo.append_intervention_plan(candidate)
    return candidate
