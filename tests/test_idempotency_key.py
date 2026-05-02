from ais.ingest import canonical_body_bytes, idempotency_key_from_parts


def test_header_wins_and_stripped() -> None:
    body = {"deliveryId": "D1", "eventType": "e", "schemaVersion": 1, "payload": {}}
    k = idempotency_key_from_parts("  my-key  ", body)
    assert k == "my-key"


def test_hash_body_when_no_header() -> None:
    body = {"a": 1, "b": 2}
    k1 = idempotency_key_from_parts(None, body)
    k2 = idempotency_key_from_parts("", body)
    assert k1 == k2
    assert len(k1) == 64


def test_canonical_bytes_stable_key_order() -> None:
    b1 = {"z": 1, "a": 2}
    b2 = {"a": 2, "z": 1}
    assert canonical_body_bytes(b1) == canonical_body_bytes(b2)
