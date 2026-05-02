from enum import StrEnum


class VoiceLifecycleState(StrEnum):
    PENDING = "pending"
    ACTIVE = "active"
    COMPLETED = "completed"
    FAILED = "failed"


def next_voice_lifecycle(
    current: VoiceLifecycleState | None,
    session_event: str | None,
) -> VoiceLifecycleState:
    """Pure transition for LiveKit-style session events (mock or real webhooks)."""
    ev = (session_event or "").strip().lower().replace("-", "_")
    if ev in ("session_started", "room_started", "started"):
        return VoiceLifecycleState.ACTIVE
    if ev in ("session_ended", "room_finished", "ended", "disconnected"):
        return VoiceLifecycleState.COMPLETED
    if ev in ("error", "session_failed", "failed"):
        return VoiceLifecycleState.FAILED
    if current is not None:
        return current
    return VoiceLifecycleState.PENDING
