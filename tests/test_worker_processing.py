import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from ais.ingest.ingress_envelope import envelope_to_json
from ais.sqs.client import ReceivedMessage
from ais.worker.processing import ProcessResult, process_ingress_message
from tests.fakes import InMemoryEventRepository


@pytest.mark.asyncio
async def test_poison_json_goes_to_dlq() -> None:
    sqs = MagicMock()
    sqs.ingress_queue_url = "u1"
    sqs.send_dlq = AsyncMock()
    sqs.delete_message = AsyncMock()
    repo = MagicMock()
    msg = ReceivedMessage(body="not json {{{", receipt_handle="rh1", receive_count=1)
    r = await process_ingress_message(
        sqs=sqs,  # type: ignore[arg-type]
        repo=repo,  # type: ignore[arg-type]
        msg=msg,
        max_receive_before_dlq=3,
    )
    assert r == ProcessResult.SENT_TO_DLQ
    repo.ingest_event.assert_not_called()
    sqs.send_dlq.assert_awaited_once()
    sqs.delete_message.assert_awaited_once_with(queue_url="u1", receipt_handle="rh1")


@pytest.mark.asyncio
async def test_invalid_payload_goes_to_dlq() -> None:
    sqs = MagicMock()
    sqs.ingress_queue_url = "u1"
    sqs.send_dlq = AsyncMock()
    sqs.delete_message = AsyncMock()
    repo = MagicMock()
    body = json.dumps({"payload": {}, "idempotencyKey": "k"})
    msg = ReceivedMessage(body=body, receipt_handle="rh1", receive_count=1)
    r = await process_ingress_message(
        sqs=sqs,  # type: ignore[arg-type]
        repo=repo,  # type: ignore[arg-type]
        msg=msg,
        max_receive_before_dlq=3,
    )
    assert r == ProcessResult.SENT_TO_DLQ
    repo.ingest_event.assert_not_called()


@pytest.mark.asyncio
async def test_valid_message_deleted_after_ingest() -> None:
    repo = InMemoryEventRepository()
    sqs = MagicMock()
    sqs.ingress_queue_url = "u1"
    sqs.delete_message = AsyncMock()
    payload = {
        "deliveryId": "Dw",
        "eventType": "location_update",
        "schemaVersion": 1,
        "payload": {"status": "in_transit"},
    }
    body = envelope_to_json(payload, "idem-w")
    msg = ReceivedMessage(body=body, receipt_handle="rh-w", receive_count=1)
    r = await process_ingress_message(
        sqs=sqs,  # type: ignore[arg-type]
        repo=repo,
        msg=msg,
        max_receive_before_dlq=3,
    )
    assert r == ProcessResult.DELETED
    assert len(repo._events) == 1  # noqa: SLF001
    assert len(repo._watchtower) == 1  # noqa: SLF001
    sqs.delete_message.assert_awaited_once_with(queue_url="u1", receipt_handle="rh-w")
