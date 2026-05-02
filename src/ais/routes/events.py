import json
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field, ValidationError

from ais.ingest import idempotency_key_from_parts, normalize_ingest_body
from ais.ingest.ingress_envelope import envelope_to_json
from ais.repositories import EventRepository, IngestOutcome

router = APIRouter(prefix="/v1", tags=["events"])


def get_event_repository(request: Request) -> EventRepository:
    repo = getattr(request.app.state, "event_repository", None)
    if repo is None:
        raise HTTPException(status_code=503, detail="Event store not configured")
    return repo


Repo = Annotated[EventRepository, Depends(get_event_repository)]


class IngestResponse(BaseModel):
    accepted: bool
    duplicate: bool
    queued: bool = False
    trace_id: str = Field(alias="traceId")
    delivery_id: str = Field(alias="deliveryId")
    idempotency_key: str = Field(alias="idempotencyKey")
    message_id: str | None = Field(default=None, alias="messageId")

    model_config = {"populate_by_name": True}


class DeliveryDetailResponse(BaseModel):
    delivery: dict[str, Any]
    events: list[dict[str, Any]]


@router.post("/events", response_model=IngestResponse)
async def post_delivery_event(request: Request, repo: Repo) -> IngestResponse:
    body_bytes = await request.body()
    try:
        data = json.loads(body_bytes.decode("utf-8"))
    except json.JSONDecodeError as e:
        raise HTTPException(status_code=400, detail="Invalid JSON body") from e
    if not isinstance(data, dict):
        raise HTTPException(status_code=400, detail="JSON body must be an object")

    header = request.headers.get("Idempotency-Key") or request.headers.get("X-Idempotency-Key")
    idem_key = idempotency_key_from_parts(header, data)

    try:
        event, trace_id = normalize_ingest_body(data)
    except ValidationError as e:
        raise HTTPException(status_code=422, detail=e.errors()) from e

    if getattr(request.app.state, "queue_ingress", False):
        sqs = getattr(request.app.state, "sqs_client", None)
        if sqs is None:
            raise HTTPException(status_code=503, detail="SQS ingress not configured")
        msg_body = envelope_to_json(data, idem_key)
        mid = await sqs.send_ingress_json(msg_body)
        return IngestResponse(
            accepted=True,
            duplicate=False,
            queued=True,
            trace_id=trace_id,
            delivery_id=event.delivery_id,
            idempotency_key=idem_key,
            message_id=mid,
        )

    out: IngestOutcome = await repo.ingest_event(
        idempotency_key=idem_key,
        event=event,
        trace_id=trace_id,
    )
    return IngestResponse(
        accepted=not out.duplicate,
        duplicate=out.duplicate,
        queued=False,
        trace_id=out.trace_id,
        delivery_id=out.delivery_id,
        idempotency_key=out.idempotency_key,
        message_id=None,
    )


@router.get("/deliveries/{delivery_id}", response_model=DeliveryDetailResponse)
async def get_delivery_detail(delivery_id: str, repo: Repo) -> DeliveryDetailResponse:
    d = await repo.get_delivery(delivery_id)
    if d is None:
        raise HTTPException(status_code=404, detail="Delivery not found")
    events = await repo.list_events_for_delivery(delivery_id)
    return DeliveryDetailResponse(
        delivery=d.model_dump(by_alias=True, mode="json"),
        events=events,
    )
