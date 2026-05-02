import uuid
from typing import Any

from ais.ingest.models import IngestPayload, payload_to_normalized
from ais.models import NormalizedEvent


def parse_ingest_payload(data: dict[str, Any]) -> IngestPayload:
    return IngestPayload.model_validate(data)


def normalize_ingest_body(data: dict[str, Any]) -> tuple[NormalizedEvent, str]:
    """Pure: validate dict → NormalizedEvent + trace id (generated if absent)."""
    p = parse_ingest_payload(data)
    ev, trace = payload_to_normalized(p)
    tid = trace or str(uuid.uuid4())
    return ev, tid
