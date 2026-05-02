"""Parse SQS body → same ingest path as HTTP API; DLQ poison + retry policy."""

from __future__ import annotations

import json
import logging
import uuid
from enum import Enum, auto

from pydantic import ValidationError

from ais.ingest import normalize_ingest_body
from ais.ingest.ingress_envelope import parse_envelope_json
from ais.logging_config import bind_correlation_id, reset_correlation_id
from ais.pipeline import run_post_ingest_pipeline
from ais.repositories import EventRepository
from ais.sqs.client import ReceivedMessage, SqsClient
from ais.watchtower.evaluator import WatchtowerEvaluator

logger = logging.getLogger(__name__)


class ProcessResult(Enum):
    DELETED = auto()
    SENT_TO_DLQ = auto()


async def process_ingress_message(
    *,
    sqs: SqsClient,
    repo: EventRepository,
    msg: ReceivedMessage,
    max_receive_before_dlq: int,
    intervention_cooldown_seconds: int = 300,
    watchtower_evaluator: WatchtowerEvaluator | None = None,
) -> ProcessResult:
    """Normalize + persist; invalid validation → DLQ; transient error → requeue via visibility."""
    ingress_url = sqs.ingress_queue_url
    raw = msg.body
    try:
        envelope = parse_envelope_json(raw)
    except (ValueError, ValidationError, json.JSONDecodeError):
        await sqs.send_dlq(raw)
        await sqs.delete_message(queue_url=ingress_url, receipt_handle=msg.receipt_handle)
        return ProcessResult.SENT_TO_DLQ

    token = bind_correlation_id(envelope.correlation_id or str(uuid.uuid4()))
    try:
        try:
            event, trace_id = normalize_ingest_body(envelope.payload)
        except ValidationError:
            await sqs.send_dlq(raw)
            await sqs.delete_message(queue_url=ingress_url, receipt_handle=msg.receipt_handle)
            return ProcessResult.SENT_TO_DLQ

        try:
            outcome = await repo.ingest_event(
                idempotency_key=envelope.idempotency_key,
                event=event,
                trace_id=trace_id,
            )
            if (not outcome.duplicate) or outcome.resume_pipeline:
                await run_post_ingest_pipeline(
                    repo,
                    outcome.delivery_id,
                    envelope.idempotency_key,
                    watchtower_evaluator=watchtower_evaluator,
                    intervention_cooldown_seconds=intervention_cooldown_seconds,
                )
            logger.info(
                "worker ingested delivery_id=%s duplicate=%s idempotency_key=%s",
                outcome.delivery_id,
                outcome.duplicate,
                envelope.idempotency_key,
            )
        except Exception:
            if msg.receive_count >= max_receive_before_dlq:
                await sqs.send_dlq(raw)
                await sqs.delete_message(queue_url=ingress_url, receipt_handle=msg.receipt_handle)
                return ProcessResult.SENT_TO_DLQ
            raise

        await sqs.delete_message(queue_url=ingress_url, receipt_handle=msg.receipt_handle)
        return ProcessResult.DELETED
    finally:
        reset_correlation_id(token)
