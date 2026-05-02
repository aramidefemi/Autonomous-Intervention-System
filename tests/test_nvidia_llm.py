import pytest

from ais.config import Settings
from ais.llm.nvidia import (
    NvidiaWatchtowerEvaluator,
    merge_watchtower_risk_with_rules,
    openai_client,
    parse_watchtower_llm_json,
    watchtower_evaluator_from_settings,
)
from ais.models import RiskLevel, WatchtowerAction, WatchtowerDecision


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
    assert d.action == WatchtowerAction.NONE
    assert d.source == "llm"
    assert d.signals == {"a": 1.0}


def test_parse_watchtower_llm_json_action_and_fallback() -> None:
    fb = WatchtowerDecision(
        deliveryId="D1",
        risk=RiskLevel.MEDIUM,
        reason="eta_slipped",
        action=WatchtowerAction.WAIT,
        action_reason="mon",
    )
    raw = '{"risk":"low","reason":"ok","action":"escalate","action_reason":"because"}'
    d = parse_watchtower_llm_json(
        raw, delivery_id="D1", signals_snapshot={}, rules_fallback=fb
    )
    assert d is not None
    assert d.action == WatchtowerAction.ESCALATE
    assert d.action_reason == "because"
    no_action = '{"risk":"low","reason":"x"}'
    d2 = parse_watchtower_llm_json(
        no_action, delivery_id="D1", signals_snapshot={}, rules_fallback=fb
    )
    assert d2 is not None
    assert d2.action == WatchtowerAction.WAIT


def test_parse_watchtower_llm_json_bad() -> None:
    assert parse_watchtower_llm_json("not json", delivery_id="D1", signals_snapshot={}) is None


def test_nvidia_evaluator_requires_client() -> None:
    s = Settings(NVIDIA_API_KEY="")
    with pytest.raises(ValueError, match="NVIDIA_API_KEY"):
        NvidiaWatchtowerEvaluator(s, client=None)


def _wd(risk: RiskLevel, reason: str) -> WatchtowerDecision:
    return WatchtowerDecision(deliveryId="D", risk=risk, reason=reason, source="rules")


@pytest.mark.parametrize(
    ("rules_r", "rules_reason", "llm_r", "expected"),
    [
        (RiskLevel.MEDIUM, "eta_slipped", RiskLevel.HIGH, RiskLevel.MEDIUM),
        (RiskLevel.MEDIUM, "eta_slipped", RiskLevel.LOW, RiskLevel.MEDIUM),
        (RiskLevel.HIGH, "stale_update", RiskLevel.LOW, RiskLevel.HIGH),
        (RiskLevel.LOW, "nominal", RiskLevel.HIGH, RiskLevel.HIGH),
        (RiskLevel.LOW, "nominal", RiskLevel.LOW, RiskLevel.LOW),
    ],
)
def test_merge_watchtower_risk_with_rules(
    rules_r: RiskLevel,
    rules_reason: str,
    llm_r: RiskLevel,
    expected: RiskLevel,
) -> None:
    out = merge_watchtower_risk_with_rules(_wd(rules_r, rules_reason), _wd(llm_r, "llm"))
    assert out == expected
