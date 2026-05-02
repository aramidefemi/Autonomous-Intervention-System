import pytest
from pydantic import ValidationError

from ais.ingest import normalize_ingest_body, parse_ingest_payload


def test_normalize_ingest_ok() -> None:
    ev, tid = normalize_ingest_body(
        {
            "deliveryId": "D1",
            "eventType": "location_update",
            "schemaVersion": 1,
            "occurredAt": "2026-05-01T12:00:00Z",
            "payload": {"status": "in_transit"},
            "traceId": "trace-abc",
        }
    )
    assert ev.delivery_id == "D1"
    assert ev.event_type == "location_update"
    assert tid == "trace-abc"


def test_normalize_generates_trace_when_missing() -> None:
    ev, tid = normalize_ingest_body(
        {
            "deliveryId": "D1",
            "eventType": "ping",
            "schemaVersion": 1,
            "payload": {},
        }
    )
    assert len(tid) == 36  # uuid
    assert ev.delivery_id == "D1"


def test_parse_rejects_bad_schema() -> None:
    with pytest.raises(ValidationError):
        parse_ingest_payload(
            {
                "deliveryId": "D1",
                "eventType": "x",
                "schemaVersion": 999,
            }
        )


def test_occurred_at_defaults_when_omitted() -> None:
    ev, _ = normalize_ingest_body(
        {
            "deliveryId": "D1",
            "eventType": "ping",
            "schemaVersion": 1,
            "payload": {},
        }
    )
    assert ev.occurred_at.tzinfo is not None
