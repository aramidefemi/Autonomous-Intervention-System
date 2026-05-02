import pytest

from ais.voice import VoiceLifecycleState, next_voice_lifecycle


@pytest.mark.parametrize(
    ("event", "expected"),
    [
        ("session_started", VoiceLifecycleState.ACTIVE),
        ("SESSION_ENDED", VoiceLifecycleState.COMPLETED),
        ("session_failed", VoiceLifecycleState.FAILED),
        ("unknown_event", VoiceLifecycleState.PENDING),
    ],
)
def test_next_voice_lifecycle_from_none(event: str, expected: VoiceLifecycleState) -> None:
    assert next_voice_lifecycle(None, event) == expected


def test_next_voice_lifecycle_preserves_current_on_unknown() -> None:
    cur = VoiceLifecycleState.ACTIVE
    assert next_voice_lifecycle(cur, "noop") is cur
