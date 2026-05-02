"""NVIDIA integrate.api OpenAI-compatible client, streaming, optional watchtower evaluator."""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Iterator
from typing import Any, NamedTuple

from openai import OpenAI

from ais.config import Settings
from ais.models import Delivery, RiskLevel, WatchtowerDecision
from ais.watchtower.evaluator import WatchtowerEvaluator
from ais.watchtower.rules import decide_from_rules, signals_snapshot
from ais.watchtower.signals import WatchtowerSignals

logger = logging.getLogger(__name__)

_STREAM_SYSTEM = (
    "You are the AI Delivery Watchtower. Given delivery signals, respond with JSON only: "
    '{"risk":"low"|"medium"|"high","reason":"<short reason>"}. '
    "No markdown fences."
)


class StreamChunk(NamedTuple):
    reasoning: str | None
    content: str | None


def openai_client(settings: Settings) -> OpenAI | None:
    if not settings.nvidia_api_key:
        return None
    return OpenAI(base_url=settings.nvidia_base_url, api_key=settings.nvidia_api_key)


def stream_nvidia_chat(
    client: OpenAI,
    *,
    model: str,
    messages: list[dict[str, str]],
    temperature: float = 1.0,
    top_p: float = 0.95,
    max_tokens: int = 16384,
    reasoning_budget: int = 16384,
    enable_thinking: bool = True,
) -> Iterator[StreamChunk]:
    """Match NVIDIA streaming pattern (reasoning_content + content chunks)."""
    stream = client.chat.completions.create(
        model=model,
        messages=messages,
        temperature=temperature,
        top_p=top_p,
        max_tokens=max_tokens,
        extra_body={
            "chat_template_kwargs": {"enable_thinking": enable_thinking},
            "reasoning_budget": reasoning_budget,
        },
        stream=True,
    )
    for chunk in stream:
        if not chunk.choices:
            continue
        delta = chunk.choices[0].delta
        reasoning = getattr(delta, "reasoning_content", None)
        if reasoning:
            yield StreamChunk(reasoning, None)
        c = delta.content
        if c is not None:
            yield StreamChunk(None, c)


def _strip_json_fences(raw: str) -> str:
    t = raw.strip()
    if not t.startswith("```"):
        return t
    lines = t.split("\n")
    if lines and lines[0].startswith("```"):
        lines = lines[1:]
    if lines and lines[-1].strip() == "```":
        lines = lines[:-1]
    return "\n".join(lines).strip()


def _json_candidates(raw: str) -> Iterator[str]:
    s = raw.strip()
    yield s
    fenced = _strip_json_fences(raw)
    if fenced != s:
        yield fenced
    i = fenced.find("{")
    j = fenced.rfind("}")
    if i >= 0 and j > i:
        yield fenced[i : j + 1]


def _parse_risk(value: object) -> RiskLevel | None:
    if not isinstance(value, str):
        return None
    key = value.strip().lower()
    for lvl in RiskLevel:
        if lvl.value == key:
            return lvl
    return None


def parse_watchtower_llm_json(
    text: str,
    *,
    delivery_id: str,
    signals_snapshot: dict[str, Any],
) -> WatchtowerDecision | None:
    """Parse model output into WatchtowerDecision; None if unparseable."""
    data: dict[str, Any] | None = None
    for cand in _json_candidates(text):
        try:
            obj = json.loads(cand)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict):
            data = obj
            break
    if data is None:
        return None
    risk = _parse_risk(data.get("risk"))
    reason = data.get("reason")
    if risk is None or not isinstance(reason, str) or not reason.strip():
        return None
    return WatchtowerDecision(
        deliveryId=delivery_id,
        risk=risk,
        reason=reason.strip(),
        signals=signals_snapshot,
        source="llm",
    )


def watchtower_evaluator_from_settings(settings: Settings) -> WatchtowerEvaluator | None:
    if openai_client(settings) is None:
        return None
    return NvidiaWatchtowerEvaluator(settings)


class NvidiaWatchtowerEvaluator:
    """Non-streaming chat completion → JSON decision; falls back to rules on failure."""

    def __init__(self, settings: Settings, *, client: OpenAI | None = None) -> None:
        self._s = settings
        self._client = client or openai_client(settings)
        if self._client is None:
            msg = "NvidiaWatchtowerEvaluator requires NVIDIA_API_KEY"
            raise ValueError(msg)

    async def evaluate(
        self,
        *,
        delivery_id: str,
        delivery: Delivery,
        signals: WatchtowerSignals,
        events: list[dict],
    ) -> WatchtowerDecision:
        snap = signals_snapshot(signals)
        payload = {
            "deliveryId": delivery_id,
            "signals": snap,
            "delivery": delivery.model_dump(by_alias=True, mode="json"),
            "recentEvents": events[-50:],
        }
        messages = [
            {"role": "system", "content": _STREAM_SYSTEM},
            {"role": "user", "content": json.dumps(payload, default=str)},
        ]

        def _sync_call() -> str:
            comp = self._client.chat.completions.create(
                model=self._s.nvidia_model,
                messages=messages,
                temperature=self._s.nvidia_temperature,
                top_p=self._s.nvidia_top_p,
                max_tokens=self._s.nvidia_max_tokens,
                extra_body={
                    "chat_template_kwargs": {"enable_thinking": self._s.nvidia_enable_thinking},
                    "reasoning_budget": self._s.nvidia_reasoning_budget,
                },
            )
            return (comp.choices[0].message.content or "").strip()

        text = await asyncio.to_thread(_sync_call)
        parsed = parse_watchtower_llm_json(text, delivery_id=delivery_id, signals_snapshot=snap)
        if parsed is not None:
            return parsed
        logger.warning("watchtower LLM parse failed; using rules. raw_len=%s", len(text))
        return decide_from_rules(signals, delivery_id=delivery_id)
