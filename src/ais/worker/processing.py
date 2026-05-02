"""Parse SQS body → same ingest path as HTTP API; DLQ poison + retry policy."""

from __future__ import annotations

import json
from enum import Enum, auto

from pydantic import ValidationError

from ais.ingest import normalize_ingest_body
from ais.ingest.ingress_envelope import parse_envelope_json
from ais.repositories import EventRepository
from ais.sqs.client import ReceivedMessage, SqsClient


class ProcessResult(Enum):
    DELETED = auto()
    SENT_TO_DLQ = auto()


async def process_ingress_message(
    *,
    sqs: SqsClient,
    repo: EventRepository,
    msg: ReceivedMessage,
    max_receive_before_dlq: int,
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

    try:
        event, trace_id = normalize_ingest_body(envelope.payload)
    except ValidationError:
        await sqs.send_dlq(raw)
        await sqs.delete_message(queue_url=ingress_url, receipt_handle=msg.receipt_handle)
        return ProcessResult.SENT_TO_DLQ

    try:
        await repo.ingest_event(
            idempotency_key=envelope.idempotency_key,
            event=event,
            trace_id=trace_id,
        )
    except Exception:
        if msg.receive_count >= max_receive_before_dlq:
            await sqs.send_dlq(raw)
            await sqs.delete_message(queue_url=ingress_url, receipt_handle=msg.receipt_handle)
            return ProcessResult.SENT_TO_DLQ
        raise

    await sqs.delete_message(queue_url=ingress_url, receipt_handle=msg.receipt_handle)
    return ProcessResult.DELETED
