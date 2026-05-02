import json

import pytest

from ais.config import Settings
from ais.models import IssueType
from ais.voice.llm_transcript import _parse_llm_payload, default_action_point, enrich_voice_callback


def test_default_action_point_covers_all_issue_types() -> None:
    for it in IssueType:
        s = default_action_point(it)
        assert isinstance(s, str) and len(s) > 4


def test_parse_llm_payload() -> None:
    it, ap = _parse_llm_payload(
        json.dumps(
            {
                "issueType": "traffic_delay",
                "actionPoint": "Notify customer of 10m slip.",
            }
        )
    )
    assert it == IssueType.TRAFFIC_DELAY
    assert ap == "Notify customer of 10m slip."


def test_parse_llm_fenced() -> None:
    it, ap = _parse_llm_payload('```json\n{"issueType":"other","actionPoint":"x"}\n```')
    assert it == IssueType.OTHER
    assert ap == "x"


@pytest.mark.asyncio
async def test_enrich_falls_back_without_llm() -> None:
    s = Settings(nvidia_api_key=None)
    out = await enrich_voice_callback(
        "stuck in traffic on the bridge",
        delivery_id="D1",
        structured=None,
        settings=s,
    )
    assert out.extraction.issue_type == IssueType.TRAFFIC_DELAY
    assert out.extraction.method == "keyword"
    assert "traffic" in out.action_point.lower() or "Monitor" in out.action_point
