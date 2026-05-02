"""Optional ElevenLabs TTS for the voice sim page (API key stays server-side)."""

from __future__ import annotations

import httpx

from ais.config import Settings

# ElevenLabs English default when ELEVENLABS_VOICE_ID is unset (Rachel)
DEFAULT_VOICE_ID = "21m00Tcm4TlvDq8ikWAM"
ELEVEN_API = "https://api.elevenlabs.io/v1"
MAX_TTS_CHARS = 4500


def elevenlabs_tts_configured(settings: Settings) -> bool:
    return bool(settings.elevenlabs_api_key)


def resolve_voice_id(settings: Settings) -> str:
    return settings.elevenlabs_voice_id or DEFAULT_VOICE_ID


async def synthesize_mpeg(*, settings: Settings, text: str) -> bytes:
    """POST text-to-speech; returns MP3 bytes."""
    if not settings.elevenlabs_api_key:
        msg = "ELEVENLABS_API_KEY not set"
        raise ValueError(msg)
    if len(text) > MAX_TTS_CHARS:
        msg = f"text exceeds {MAX_TTS_CHARS} characters"
        raise ValueError(msg)
    voice_id = resolve_voice_id(settings)
    url = f"{ELEVEN_API}/text-to-speech/{voice_id}"
    payload = {"text": text, "model_id": settings.elevenlabs_model_id}
    async with httpx.AsyncClient(timeout=60.0) as client:
        r = await client.post(
            url,
            headers={
                "xi-api-key": settings.elevenlabs_api_key,
                "Accept": "audio/mpeg",
                "Content-Type": "application/json",
            },
            json=payload,
        )
    if r.status_code >= 400:
        msg = r.text[:1200] if r.text else r.reason_phrase
        raise RuntimeError(f"ElevenLabs HTTP {r.status_code}: {msg}")
    return r.content
