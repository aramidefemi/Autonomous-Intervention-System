import json
import logging
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field, ValidationError

from ais.concurrency.revision import expected_revision_allows_ingest
from ais.ingest import idempotency_key_from_parts, normalize_ingest_body
from ais.ingest.ingress_envelope import envelope_to_json
from ais.logging_config import get_correlation_id
from ais.pipeline import run_post_ingest_pipeline
from ais.repositories import EventRepository, IngestOutcome

router = APIRouter(prefix="/v1", tags=["events"])
logger = logging.getLogger(__name__)


def get_event_repository(request: Request) -> EventRepository:
    repo = getattr(request.app.state, "event_repository", None)
    if repo is None:
        raise HTTPException(status_code=503, detail="Event store not configured")
    return repo


Repo = Annotated[EventRepository, Depends(get_event_repository)]


def _parse_expected_revision(request: Request) -> int | None:
    raw = request.headers.get("X-Expected-Delivery-Revision")
    if raw is None or raw == "":
        return None
    try:
        return int(raw)
    except ValueError:
        raise HTTPException(
            status_code=422,
            detail="Invalid X-Expected-Delivery-Revision",
        ) from None


async def _guard_delivery_revision(
    repo: EventRepository,
    delivery_id: str,
    request: Request,
) -> None:
    expected = _parse_expected_revision(request)
    if expected is None:
        return
    existing = await repo.get_delivery(delivery_id)
    cur = existing.revision if existing else None
    if not expected_revision_allows_ingest(expected=expected, current_revision=cur):
        raise HTTPException(
            status_code=409,
            detail={
                "error": "revision_conflict",
                "currentRevision": cur if existing is not None else 0,
            },
        )


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
    watchtower_decisions: list[dict[str, Any]] = Field(
        default_factory=list,
        alias="watchtowerDecisions",
    )
    intervention_plans: list[dict[str, Any]] = Field(
        default_factory=list,
        alias="interventionPlans",
    )
    voice_outcomes: list[dict[str, Any]] = Field(
        default_factory=list,
        alias="voiceOutcomes",
    )

    model_config = {"populate_by_name": True}


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

    await _guard_delivery_revision(repo, event.delivery_id, request)

    if getattr(request.app.state, "queue_ingress", False):
        sqs = getattr(request.app.state, "sqs_client", None)
        if sqs is None:
            raise HTTPException(status_code=503, detail="SQS ingress not configured")
        msg_body = envelope_to_json(
            data,
            idem_key,
            correlation_id=get_correlation_id(),
        )
        mid = await sqs.send_ingress_json(msg_body)
        logger.info(
            "queued ingress delivery_id=%s idempotency_key=%s",
            event.delivery_id,
            idem_key,
        )
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
    if (not out.duplicate) or out.resume_pipeline:
        ev = getattr(request.app.state, "watchtower_evaluator", None)
        s = getattr(request.app.state, "settings", None)
        cooldown = getattr(s, "intervention_cooldown_seconds", 300) if s is not None else 300
        await run_post_ingest_pipeline(
            repo,
            out.delivery_id,
            idem_key,
            watchtower_evaluator=ev,
            intervention_cooldown_seconds=cooldown,
        )
    processed = (not out.duplicate) or out.resume_pipeline
    logger.info(
        "ingested delivery_id=%s duplicate=%s processed=%s idempotency_key=%s",
        out.delivery_id,
        out.duplicate,
        processed,
        out.idempotency_key,
    )
    return IngestResponse(
        accepted=processed,
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
    decisions = await repo.list_watchtower_decisions(delivery_id)
    plans = await repo.list_intervention_plans(delivery_id)
    voice = await repo.list_voice_outcomes(delivery_id)
    return DeliveryDetailResponse(
        delivery=d.model_dump(by_alias=True, mode="json"),
        events=events,
        watchtowerDecisions=decisions,
        interventionPlans=plans,
        voiceOutcomes=voice,
    )
