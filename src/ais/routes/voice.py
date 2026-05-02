from typing import Annotated, Any

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, Response
from pydantic import BaseModel, Field

from ais.config import Settings
from ais.models import VoiceSessionOutcome
from ais.repositories import EventRepository
from ais.routes.voice_sim_ui import render_voice_simulate_page
from ais.voice import next_voice_lifecycle
from ais.voice.llm_transcript import enrich_voice_callback
from ais.voice.elevenlabs_tts import (
    elevenlabs_tts_configured,
    synthesize_mpeg,
)
from ais.voice.livekit_sim import build_simulation_join, normalize_livekit_url
from ais.voice.ops_opening import build_ops_opening_line

router = APIRouter(prefix="/v1", tags=["voice"])


def get_event_repository(request: Request) -> EventRepository:
    repo = getattr(request.app.state, "event_repository", None)
    if repo is None:
        raise HTTPException(status_code=503, detail="Event store not configured")
    return repo


Repo = Annotated[EventRepository, Depends(get_event_repository)]


def get_settings(request: Request) -> Settings:
    return request.app.state.settings


SettingsDep = Annotated[Settings, Depends(get_settings)]


def _livekit_configured(s: Settings) -> bool:
    return bool(s.livekit_url and s.livekit_api_key and s.livekit_api_secret)


class VoiceSimulateSessionRequest(BaseModel):
    delivery_id: str = Field(..., min_length=1, alias="deliveryId")

    model_config = {"populate_by_name": True}


class VoiceSimulateSessionResponse(BaseModel):
    livekit_url: str = Field(alias="livekitUrl")
    room_name: str = Field(alias="roomName")
    token: str
    identity: str
    join_page_url: str = Field(alias="joinPageUrl")
    opening_line: str = Field(alias="openingLine")
    opening_source: str = Field(alias="openingSource")

    model_config = {"populate_by_name": True}


class VoiceSimulateOpeningResponse(BaseModel):
    opening_line: str = Field(alias="openingLine")
    opening_source: str = Field(alias="openingSource")

    model_config = {"populate_by_name": True}


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
    action_point: str = Field(default="", alias="actionPoint")
    lifecycle: str

    model_config = {"populate_by_name": True}


class VoiceTtsRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=4500)

    model_config = {"populate_by_name": True}


@router.post("/voice/simulate/session", response_model=VoiceSimulateSessionResponse)
async def post_voice_simulate_session(
    body: VoiceSimulateSessionRequest,
    repo: Repo,
    request: Request,
    settings: SettingsDep,
) -> VoiceSimulateSessionResponse:
    """Room token for browser WebRTC. PSTN/SIP is a separate step."""
    d = await repo.get_delivery(body.delivery_id)
    if d is None:
        raise HTTPException(status_code=404, detail="Delivery not found")
    opening_line, opening_source = await build_ops_opening_line(
        repo,
        body.delivery_id,
        settings,
    )
    if not _livekit_configured(settings):
        raise HTTPException(
            status_code=503,
            detail="LiveKit not configured: set LIVEKIT_URL, LIVEKIT_API_KEY, LIVEKIT_API_SECRET",
        )
    assert settings.livekit_api_key and settings.livekit_api_secret and settings.livekit_url
    join = build_simulation_join(
        api_key=settings.livekit_api_key,
        api_secret=settings.livekit_api_secret,
        delivery_id=body.delivery_id,
    )
    join_url = str(request.url_for("voice_simulate_ui", delivery_id=body.delivery_id))
    return VoiceSimulateSessionResponse(
        livekitUrl=normalize_livekit_url(settings.livekit_url),
        roomName=join.room_name,
        token=join.token,
        identity=join.identity,
        joinPageUrl=join_url,
        openingLine=opening_line,
        openingSource=opening_source,
    )


@router.get(
    "/voice/simulate/opening/{delivery_id}",
    response_model=VoiceSimulateOpeningResponse,
)
async def get_voice_simulate_opening(
    delivery_id: str,
    repo: Repo,
    settings: SettingsDep,
) -> VoiceSimulateOpeningResponse:
    """AI (or rules) one-liner for the sim UI — uses delivery events, watchtower, interventions."""
    try:
        line, source = await build_ops_opening_line(repo, delivery_id, settings)
    except ValueError:
        raise HTTPException(status_code=404, detail="Delivery not found") from None
    return VoiceSimulateOpeningResponse(openingLine=line, openingSource=source)


@router.post("/voice/tts")
async def post_voice_tts(body: VoiceTtsRequest, settings: SettingsDep) -> Response:
    """Generate spoken audio for the browser sim. Requires ``ELEVENLABS_API_KEY``."""
    if not elevenlabs_tts_configured(settings):
        raise HTTPException(
            status_code=503,
            detail="ElevenLabs not configured: set ELEVENLABS_API_KEY",
        )
    try:
        audio = await synthesize_mpeg(settings=settings, text=body.text.strip())
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=str(e)) from e
    except httpx.HTTPError as e:
        raise HTTPException(status_code=502, detail=str(e)) from e
    return Response(content=audio, media_type="audio/mpeg")


@router.get(
    "/voice/simulate/ui/{delivery_id}",
    response_class=HTMLResponse,
    name="voice_simulate_ui",
)
async def get_voice_simulate_ui(
    delivery_id: str,
    repo: Repo,
    settings: SettingsDep,
) -> HTMLResponse:
    """Single-page WebRTC sim: open this URL in a browser, Connect → optional POST callback."""
    if not _livekit_configured(settings):
        raise HTTPException(
            status_code=503,
            detail="LiveKit not configured: set LIVEKIT_URL, LIVEKIT_API_KEY, LIVEKIT_API_SECRET",
        )
    d = await repo.get_delivery(delivery_id)
    if d is None:
        raise HTTPException(status_code=404, detail="Delivery not found")
    return HTMLResponse(
        content=render_voice_simulate_page(
            delivery_id,
            use_elevenlabs=elevenlabs_tts_configured(settings),
        ),
    )


@router.post("/voice/callback", response_model=VoiceCallbackResponse)
async def post_voice_callback(
    body: VoiceCallbackRequest,
    repo: Repo,
    settings: SettingsDep,
) -> VoiceCallbackResponse:
    d = await repo.get_delivery(body.delivery_id)
    if d is None:
        raise HTTPException(status_code=404, detail="Delivery not found")

    enriched = await enrich_voice_callback(
        body.transcript,
        delivery_id=body.delivery_id,
        structured=body.structured,
        settings=settings,
    )
    ext = enriched.extraction
    ls = next_voice_lifecycle(None, body.session_event)
    merged_structured: dict[str, Any] = dict(body.structured or {})
    merged_structured["actionPoint"] = enriched.action_point
    outcome = VoiceSessionOutcome(
        deliveryId=body.delivery_id,
        roomName=body.room_name,
        transcript=body.transcript,
        issueType=ext.issue_type,
        actionPoint=enriched.action_point,
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
        actionPoint=enriched.action_point,
        lifecycle=ls.value,
    )
