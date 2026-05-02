"""Unit tests for ops opening line post-processing (TTS-safe text)."""

from ais.voice.ops_opening import _clean_llm_line


def test_clean_llm_line_plain() -> None:
    assert (
        _clean_llm_line(
            "Hey, checking in on delivery D-abc — location looks stale, everything okay?",
            "D-abc",
        )
        == "Hey, checking in on delivery D-abc — location looks stale, everything okay?"
    )


def test_clean_llm_line_strips_meta_prefix() -> None:
    out = _clean_llm_line(
        "What to say: Hey, it's ops on delivery D-abc. What's your ETA looking like?",
        "D-abc",
    )
    assert out.startswith("Hey")
    assert "What to say" not in out


def test_clean_llm_line_think_block() -> None:
    raw = (
        "<think>\nreasoning here\n</think>\n\n"
        "Hey, it's ops checking delivery D-x — you good?"
    )
    out = _clean_llm_line(raw, "D-x")
    assert "reasoning" not in out.casefold()
    assert "D-x" in out


def test_clean_llm_line_prefers_paragraph_with_delivery_id() -> None:
    raw = "I'll be concise.\n\nPlease ask about delay.\n\nHey, it's ops on D-z — still moving?"
    out = _clean_llm_line(raw, "D-z")
    assert "D-z" in out
    assert "Please ask" not in out
