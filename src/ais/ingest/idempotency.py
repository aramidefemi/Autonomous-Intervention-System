import hashlib
import json
from typing import Any


def canonical_body_bytes(body: dict[str, Any]) -> bytes:
    return json.dumps(body, sort_keys=True, separators=(",", ":")).encode("utf-8")


def idempotency_key_from_parts(header_value: str | None, body: dict[str, Any]) -> str:
    if header_value is not None and (key := header_value.strip()):
        return key
    return hashlib.sha256(canonical_body_bytes(body)).hexdigest()
