"""SQS consumer: same normalization + Mongo ingest as POST /v1/events."""

from __future__ import annotations

import asyncio
import logging

from motor.motor_asyncio import AsyncIOMotorClient

from ais.config import Settings
from ais.llm import watchtower_evaluator_from_settings
from ais.logging_config import configure_logging
from ais.repositories import EventRepository, MongoEventRepository
from ais.sqs.client import SqsClient
from ais.watchtower.evaluator import WatchtowerEvaluator
from ais.worker.processing import process_ingress_message
from ais.worker.retry_policy import visibility_delay_seconds

logger = logging.getLogger(__name__)


async def run_one_cycle(
    *,
    settings: Settings,
    sqs: SqsClient,
    repo: EventRepository,
    watchtower_evaluator: WatchtowerEvaluator | None,
    use_watchtower_graph: bool | None = None,
) -> int:
    """Receive up to 10 messages, process; returns count handled (deleted or DLQ)."""
    await sqs.ensure_queue_urls()
    msgs = await sqs.receive_messages(
        queue_url=sqs.ingress_queue_url,
        max_messages=10,
        visibility_timeout=settings.sqs_visibility_timeout,
        wait_time_seconds=settings.sqs_wait_time_seconds,
    )
    n = 0
    for msg in msgs:
        try:
            await process_ingress_message(
                sqs=sqs,
                repo=repo,
                msg=msg,
                max_receive_before_dlq=settings.sqs_max_receive_before_dlq,
                intervention_cooldown_seconds=settings.intervention_cooldown_seconds,
                watchtower_evaluator=watchtower_evaluator,
                use_watchtower_graph=use_watchtower_graph,
            )
            n += 1
        except Exception:
            delay = visibility_delay_seconds(attempt=msg.receive_count)
            logger.exception(
                "ingress handler failed; extending visibility by %ss",
                delay,
            )
            await sqs.change_visibility(
                queue_url=sqs.ingress_queue_url,
                receipt_handle=msg.receipt_handle,
                visibility_timeout=delay,
            )
    return n


async def run_forever(settings: Settings | None = None) -> None:
    s = settings or Settings()
    sqs_c = SqsClient(s)
    await sqs_c.ensure_queue_urls()
    mc = AsyncIOMotorClient(s.mongo_uri)
    repo = MongoEventRepository(mc[s.mongo_database])
    await repo.ensure_indexes()
    w_ev = watchtower_evaluator_from_settings(s)
    try:
        while True:
            await run_one_cycle(
                settings=s,
                sqs=sqs_c,
                repo=repo,
                watchtower_evaluator=w_ev,
                use_watchtower_graph=s.watchtower_graph_enabled,
            )
            await asyncio.sleep(0)
    finally:
        mc.close()


def main() -> None:
    configure_logging()
    asyncio.run(run_forever())
