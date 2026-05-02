"""Evaluators: default rules engine; LLM or tests implement the same protocol."""

from typing import Protocol

from ais.models import Delivery, WatchtowerDecision
from ais.watchtower.rules import decide_from_rules
from ais.watchtower.signals import WatchtowerSignals


class WatchtowerEvaluator(Protocol):
    async def evaluate(
        self,
        *,
        delivery_id: str,
        delivery: Delivery,
        signals: WatchtowerSignals,
        events: list[dict],
    ) -> WatchtowerDecision: ...


class RulesEvaluator:
    async def evaluate(
        self,
        *,
        delivery_id: str,
        delivery: Delivery,
        signals: WatchtowerSignals,
        events: list[dict],
    ) -> WatchtowerDecision:
        _ = delivery, events
        return decide_from_rules(signals, delivery_id=delivery_id)
