import json

import pytest

from ais.ingest.ingress_envelope import (
    envelope_to_json,
    parse_envelope_json,
)


def test_envelope_round_trip() -> None:
    p = {
        "deliveryId": "D1",
        "eventType": "x",
        "schemaVersion": 1,
        "payload": {"status": "ok"},
    }
    raw = envelope_to_json(p, "k1")
    d = json.loads(raw)
    assert d["idempotencyKey"] == "k1"
    assert "correlationId" not in d
    e = parse_envelope_json(raw)
    assert e.idempotency_key == "k1"
    assert e.payload == p


def test_envelope_correlation_optional_round_trip() -> None:
    p = {"deliveryId": "D1", "eventType": "x", "schemaVersion": 1, "payload": {}}
    raw = envelope_to_json(p, "k2", correlation_id="cid-1")
    d = json.loads(raw)
    assert d["correlationId"] == "cid-1"
    assert parse_envelope_json(raw).correlation_id == "cid-1"


def test_parse_rejects_non_object() -> None:
    with pytest.raises(ValueError, match="envelope must be a JSON object"):
        parse_envelope_json("[]")
