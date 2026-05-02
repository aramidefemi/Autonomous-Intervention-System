"""JSON envelope for SQS ingress (same payload shape as HTTP POST body)."""

from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel, Field


class IngressEnvelope(BaseModel):
    payload: dict[str, Any]
    idempotency_key: str = Field(alias="idempotencyKey")

    model_config = {"populate_by_name": True}


def envelope_to_json(payload: dict[str, Any], idempotency_key: str) -> str:
    env = IngressEnvelope(payload=payload, idempotency_key=idempotency_key)
    return env.model_dump_json(by_alias=True)


def parse_envelope_json(raw: str) -> IngressEnvelope:
    data = json.loads(raw)
    if not isinstance(data, dict):
        msg = "envelope must be a JSON object"
        raise ValueError(msg)
    return IngressEnvelope.model_validate(data)


def is_poison_body(raw: str) -> bool:
    """True if body cannot be parsed as envelope JSON (invalid JSON or wrong shape)."""
    try:
        parse_envelope_json(raw)
    except Exception:
        return True
    else:
        return False
