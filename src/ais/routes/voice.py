from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from ais.models import VoiceSessionOutcome
from ais.repositories import EventRepository
from ais.voice import extract_issue_type, next_voice_lifecycle

router = APIRouter(prefix="/v1", tags=["voice"])


def get_event_repository(request: Request) -> EventRepository:
    repo = getattr(request.app.state, "event_repository", None)
    if repo is None:
        raise HTTPException(status_code=503, detail="Event store not configured")
    return repo


Repo = Annotated[EventRepository, Depends(get_event_repository)]


class VoiceCallbackRequest(BaseModel):
    """Contract-style payload for LiveKit (or mock) session callbacks."""

    delivery_id: str = Field(..., min_length=1, alias="deliveryId")
    room_name: str = Field(..., min_length=1, alias="roomName")
    transcript: str = ""
    session_event: str | None = Field(default="session_ended", alias="sessionEvent")
    structured: dict[str, Any] | None = None
    source: str = Field(default="livekit_webhook")

    model_config = {"populate_by_name": True}


class VoiceCallbackResponse(BaseModel):
    accepted: bool
    issue_type: str = Field(alias="issueType")
    lifecycle: str

    model_config = {"populate_by_name": True}


@router.post("/voice/callback", response_model=VoiceCallbackResponse)
async def post_voice_callback(body: VoiceCallbackRequest, repo: Repo) -> VoiceCallbackResponse:
    d = await repo.get_delivery(body.delivery_id)
    if d is None:
        raise HTTPException(status_code=404, detail="Delivery not found")

    ext = extract_issue_type(body.transcript, structured=body.structured)
    ls = next_voice_lifecycle(None, body.session_event)
    merged_structured: dict[str, Any] = dict(body.structured or {})
    outcome = VoiceSessionOutcome(
        deliveryId=body.delivery_id,
        roomName=body.room_name,
        transcript=body.transcript,
        issueType=ext.issue_type,
        structured=merged_structured,
        lifecycle=ls.value,
        source=body.source,
        extractionConfidence=ext.confidence,
        extractionMethod=ext.method,
    )
    await repo.append_voice_outcome(outcome)
    return VoiceCallbackResponse(
        accepted=True,
        issueType=ext.issue_type.value,
        lifecycle=ls.value,
    )
