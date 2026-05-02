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
) -> InterventionPlan | None:
    t = now if now is not None else datetime.now(UTC)
    candidate = intervention_plan_from_decision(decision, planned_at=t)
    if candidate is None:
        return None
    last_at = await repo.last_intervention_planned_at(decision.delivery_id)
    if is_within_cooldown(t, last_at, cooldown_seconds):
        return None
    await repo.append_intervention_plan(candidate)
    return candidate
