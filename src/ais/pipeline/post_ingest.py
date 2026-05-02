"""Run watchtower + planner + checkpoint clear for one ingest idempotency key."""

from __future__ import annotations

from ais.planner import run_intervention_planner
from ais.repositories import EventRepository
from ais.watchtower import run_watchtower
from ais.watchtower.evaluator import WatchtowerEvaluator


async def run_post_ingest_pipeline(
    repo: EventRepository,
    delivery_id: str,
    idempotency_key: str,
    *,
    watchtower_evaluator: WatchtowerEvaluator | None = None,
    intervention_cooldown_seconds: int = 300,
    use_watchtower_graph: bool | None = None,
) -> None:
    decision = await run_watchtower(
        repo,
        delivery_id,
        evaluator=watchtower_evaluator,
        ingest_idempotency_key=idempotency_key,
        use_watchtower_graph=use_watchtower_graph,
    )
    if decision is not None:
        await run_intervention_planner(
            repo,
            decision,
            cooldown_seconds=intervention_cooldown_seconds,
            ingest_idempotency_key=idempotency_key,
        )
    await repo.complete_pipeline(delivery_id, idempotency_key)
