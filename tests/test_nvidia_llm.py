import pytest

from ais.config import Settings
from ais.llm.nvidia import (
    NvidiaWatchtowerEvaluator,
    openai_client,
    parse_watchtower_llm_json,
    watchtower_evaluator_from_settings,
)
from ais.models import RiskLevel


def test_openai_client_none_without_key() -> None:
    s = Settings(NVIDIA_API_KEY="")
    assert openai_client(s) is None


def test_watchtower_evaluator_none_without_key() -> None:
    s = Settings(NVIDIA_API_KEY="")
    assert watchtower_evaluator_from_settings(s) is None


@pytest.mark.parametrize(
    ("raw", "risk", "reason"),
    [
        ('{"risk":"high","reason":"bike issue"}', RiskLevel.HIGH, "bike issue"),
        ('```json\n{"risk":"low","reason":"ok"}\n```', RiskLevel.LOW, "ok"),
        ('prefix {"risk":"medium","reason":"x"} suffix', RiskLevel.MEDIUM, "x"),
    ],
)
def test_parse_watchtower_llm_json_ok(raw: str, risk: RiskLevel, reason: str) -> None:
    d = parse_watchtower_llm_json(
        raw,
        delivery_id="D1",
        signals_snapshot={"a": 1.0},
    )
    assert d is not None
    assert d.delivery_id == "D1"
    assert d.risk == risk
    assert d.reason == reason
    assert d.source == "llm"
    assert d.signals == {"a": 1.0}


def test_parse_watchtower_llm_json_bad() -> None:
    assert (
        parse_watchtower_llm_json("not json", delivery_id="D1", signals_snapshot={}) is None
    )


def test_nvidia_evaluator_requires_client() -> None:
    s = Settings(NVIDIA_API_KEY="")
    with pytest.raises(ValueError, match="NVIDIA_API_KEY"):
        NvidiaWatchtowerEvaluator(s, client=None)
