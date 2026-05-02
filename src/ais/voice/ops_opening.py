"""One-sentence operations check-in line: LLM with delivery context, or rules fallback."""

from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from collections import OrderedDict
from typing import Any

from openai import OpenAI

from ais.config import Settings
from ais.llm.nvidia import openai_client
from ais.repositories import EventRepository

logger = logging.getLogger(__name__)

OPS_OPENING_SYSTEM = (
    "You are a delivery operations dispatcher about to speak to a rider or customer on a quick "
    "phone check-in. Your entire reply is read verbatim by text-to-speech on a live call — it must "
    "be only the words spoken to the human: one or two short sentences, natural speech. "
    "Use the situation data; name the delivery id. Be warm and direct, not corporate mush. "
    "No preamble, analysis, labels (e.g. 'Response:'), stage directions, bullets, JSON, or emojis."
)

# revision-aware cache: avoid duplicate LLM calls while UI loads + POST session (~seconds apart)
_CACHE_MAX = 128
_cache: OrderedDict[str, tuple[str, str, float]] = OrderedDict()


def _cache_key(delivery_id: str, revision: int) -> str:
    return f"{delivery_id}:{revision}"


def _cache_get(key: str) -> tuple[str, str] | None:
    row = _cache.get(key)
    if row is None:
        return None
    line, source, ts = row
    if time.monotonic() - ts > 90:
        _cache.pop(key, None)
        return None
    _cache.move_to_end(key)
    return line, source


def _cache_set(key: str, line: str, source: str) -> None:
    _cache[key] = (line, source, time.monotonic())
    _cache.move_to_end(key)
    while len(_cache) > _CACHE_MAX:
        _cache.popitem(last=False)


def _compact_context(
    delivery_id: str,
    status: str,
    metadata: dict[str, Any],
    events: list[dict],
    watchtower: list[dict],
    plans: list[dict],
) -> dict[str, Any]:
    ev_tail = events[-8:] if events else []
    wt = watchtower[0] if watchtower else None
    pl = plans[0] if plans else None
    return {
        "deliveryId": delivery_id,
        "status": status,
        "metadataSummary": {k: metadata[k] for k in list(metadata)[:12]},
        "recentEventSample": [
            {
                "type": e.get("event_type"),
                "at": str(e.get("occurred_at")),
                "payload": e.get("payload"),
            }
            for e in ev_tail
        ],
        "latestWatchtower": wt,
        "latestInterventionPlan": pl,
    }


def _rules_fallback(ctx: dict[str, Any]) -> str:
    did = str(ctx.get("deliveryId") or "")
    st = str(ctx.get("status") or "unknown")
    wt = ctx.get("latestWatchtower")
    reason = ""
    if isinstance(wt, dict):
        reason = str(wt.get("reason") or "").strip()
    if reason:
        return (
            f"Hey, it's operations checking in on delivery {did}. We're seeing: {reason}. "
            "What's going on on your end?"
        )
    return (
        f"Hey, it's operations checking in on delivery {did}. Status shows {st}. "
        "What's going on — anything we should know?"
    )


_META_START = re.compile(
    r"(?is)^\s*(?:"
    r"here(?:'s|\s+is)\s+(?:what|a)\s+(?:you|i|we)\s+(?:should|could|can)\s+say[:.\s]+"
    r"|what\s+(?:to\s+)?say[:.\s]+"
    r"|(?:the\s+)?(?:line|reply|response|output)(?:\s+to\s+say)?[:.\s]+"
    r"|(?:spoken\s+)?(?:line|script)[:.\s]+"
    r")+"
)

_THINK_BLOCKS = re.compile(
    r"(?is)(?:<think>.*?</think>|\[thinking\].*?\[/thinking\])"
)


def _pick_spoken_paragraph(text: str, delivery_id: str) -> str:
    """When the model returns chatter + script, keep the paragraph meant for TTS."""
    t = text.strip()
    if "\n" not in t:
        return t
    parts = [p.strip() for p in re.split(r"\n\s*\n+", t) if p.strip()]
    if not parts:
        return t
    did_cf = delivery_id.casefold()
    hits = [p for p in parts if delivery_id and did_cf in p.casefold()]
    if hits:
        return max(hits, key=len)
    return parts[-1]


def _clean_llm_line(raw: str, delivery_id: str) -> str:
    t = raw.strip()
    t = _THINK_BLOCKS.sub(" ", t)
    t = _pick_spoken_paragraph(t, delivery_id)
    while True:
        u = _META_START.sub("", t)
        if u == t:
            break
        t = u.strip()
    t = re.sub(r"^[\"']|[\"']$", "", t.strip())
    t = re.sub(r"\s+", " ", t)
    if "```" in t:
        t = t.replace("```", " ")
    t = t.strip()
    if len(t) > 420:
        t = t[:417] + "…"
    if not t:
        return ""
    low = t.casefold()
    did_cf = delivery_id.casefold()
    if delivery_id and did_cf not in low:
        t = f"Hey, it's operations checking in on delivery {delivery_id}. {t}"
    return t


def _llm_opening_sync(client: OpenAI, settings: Settings, ctx: dict[str, Any]) -> str:
    payload = json.dumps(ctx, default=str)
    if len(payload) > 12_000:
        payload = payload[:12_000] + "…"
    r = client.chat.completions.create(
        model=settings.nvidia_model,
        messages=[
            {"role": "system", "content": OPS_OPENING_SYSTEM},
            {"role": "user", "content": payload},
        ],
        temperature=0.45,
        max_tokens=140,
        extra_body={
            # Voice must receive plain speakable text only; thinking belongs in a separate channel
            # and often leaks into `content` when enabled on Nemotron-class models.
            "chat_template_kwargs": {"enable_thinking": False},
            "reasoning_budget": 0,
        },
    )
    msg = r.choices[0].message
    return (msg.content or "").strip()


async def build_ops_opening_line(
    repo: EventRepository,
    delivery_id: str,
    settings: Settings,
) -> tuple[str, str]:
    d = await repo.get_delivery(delivery_id)
    if d is None:
        msg = "Delivery not found"
        raise ValueError(msg)

    events = await repo.list_events_for_delivery(delivery_id, limit=30)
    wt = await repo.list_watchtower_decisions(delivery_id, limit=5)
    plans = await repo.list_intervention_plans(delivery_id, limit=5)

    ctx = _compact_context(
        d.delivery_id,
        d.status,
        dict(d.metadata),
        events,
        wt,
        plans,
    )
    key = _cache_key(delivery_id, d.revision)
    hit = _cache_get(key)
    if hit:
        return hit[0], hit[1]

    client = openai_client(settings)
    if client is None:
        line = _rules_fallback(ctx)
        _cache_set(key, line, "rules")
        return line, "rules"

    try:
        raw = await asyncio.to_thread(_llm_opening_sync, client, settings, ctx)
        line = _clean_llm_line(raw, d.delivery_id)
        if not line:
            line = _rules_fallback(ctx)
            src = "rules"
        else:
            src = "llm"
    except Exception:
        logger.exception("ops opening LLM failed for %s", delivery_id)
        line = _rules_fallback(ctx)
        src = "rules"

    _cache_set(key, line, src)
    return line, src
