"""Duplicate ingest resumes incomplete pipeline (Phase 6)."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from ais.ingest.ingress_envelope import envelope_to_json
from ais.models import NormalizedEvent
from ais.pipeline import run_post_ingest_pipeline
from ais.sqs.client import ReceivedMessage
from ais.worker.processing import ProcessResult, process_ingress_message
from tests.fakes import InMemoryEventRepository


@pytest.mark.asyncio
async def test_duplicate_with_open_pipeline_flag_resumes_then_idempotent() -> None:
    repo = InMemoryEventRepository()
    ev = NormalizedEvent(
        deliveryId="D-res",
        eventType="location_update",
        schemaVersion=1,
        payload={"status": "in_transit"},
    )
    o1 = await repo.ingest_event(idempotency_key="rk", event=ev, trace_id="t1")
    assert not o1.duplicate
    o2 = await repo.ingest_event(idempotency_key="rk", event=ev, trace_id="t1")
    assert o2.duplicate and o2.resume_pipeline
    await run_post_ingest_pipeline(repo, ev.delivery_id, "rk")
    d = await repo.get_delivery(ev.delivery_id)
    assert d is not None
    assert d.open_pipeline_idempotency_key is None
    assert d.last_processed_seq == 1
    o3 = await repo.ingest_event(idempotency_key="rk", event=ev, trace_id="t1")
    assert o3.duplicate and not o3.resume_pipeline


@pytest.mark.asyncio
async def test_worker_processes_duplicate_resume_without_double_intervention() -> None:
    repo = InMemoryEventRepository()
    payload = {
        "deliveryId": "D-w",
        "eventType": "location_update",
        "schemaVersion": 1,
        "payload": {"status": "in_transit"},
    }
    body = envelope_to_json(payload, "idem-w2")
    msg = ReceivedMessage(body=body, receipt_handle="rh1", receive_count=1)
    sqs = MagicMock()
    sqs.ingress_queue_url = "u"
    sqs.delete_message = AsyncMock()
    r1 = await process_ingress_message(
        sqs=sqs,  # type: ignore[arg-type]
        repo=repo,
        msg=msg,
        max_receive_before_dlq=5,
        intervention_cooldown_seconds=3600,
    )
    assert r1 == ProcessResult.DELETED
    n_int = len(repo._interventions)  # noqa: SLF001
    msg2 = ReceivedMessage(body=body, receipt_handle="rh2", receive_count=2)
    r2 = await process_ingress_message(
        sqs=sqs,  # type: ignore[arg-type]
        repo=repo,
        msg=msg2,
        max_receive_before_dlq=5,
        intervention_cooldown_seconds=3600,
    )
    assert r2 == ProcessResult.DELETED
    assert len(repo._interventions) == n_int  # noqa: SLF001
