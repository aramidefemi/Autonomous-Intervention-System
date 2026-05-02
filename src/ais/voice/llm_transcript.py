"""LLM-backed transcript classification + action point for voice callbacks (LiveKit, etc.)."""

from __future__ import annotations

import asyncio
import json
import logging
import re
from dataclasses import dataclass

from openai import OpenAI

from ais.config import Settings
from ais.llm.nvidia import openai_client
from ais.models import IssueType
from ais.voice.extraction import IssueExtraction, extract_issue_type

logger = logging.getLogger(__name__)


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


def _json_candidates(raw: str) -> list[str]:
    s = raw.strip()
    out: list[str] = [s]
    fenced = _strip_json_fences(raw)
    if fenced != s:
        out.append(fenced)
    i = fenced.find("{")
    j = fenced.rfind("}")
    if i >= 0 and j > i:
        out.append(fenced[i : j + 1])
    return out


VOICE_LLM_SYSTEM = (
    "You classify short transcripts from delivery operations check-in calls (rider or customer). "
    "Reply with JSON only, no markdown fences: "
    '{"issueType":"mechanical_failure"|"traffic_delay"|"wrong_address"|'
    '"customer_unreachable"|"other"|"unknown",'
    '"actionPoint":"<one concrete next step for dispatch/ops, under 240 characters>"} '
    "actionPoint must be specific and operational (what to do next), not a recap."
)

_DEFAULT_ACTIONS: dict[IssueType, str] = {
    IssueType.MECHANICAL_FAILURE: "Arrange vehicle or equipment support; update customer on delay.",
    IssueType.TRAFFIC_DELAY: "Monitor ETA; notify customer if window slips further.",
    IssueType.WRONG_ADDRESS: "Confirm address with customer; update route in the app if needed.",
    IssueType.CUSTOMER_UNREACHABLE: "Retry contact; consider safe drop or hold per policy.",
    IssueType.OTHER: "Review notes and follow up with the rider if the issue persists.",
    IssueType.UNKNOWN: "Review delivery state and follow up with the rider if needed.",
}


def default_action_point(issue: IssueType) -> str:
    return _DEFAULT_ACTIONS.get(issue, _DEFAULT_ACTIONS[IssueType.UNKNOWN])


@dataclass(frozen=True)
class VoiceEnrichment:
    extraction: IssueExtraction
    action_point: str


def _parse_llm_payload(text: str) -> tuple[IssueType | None, str | None]:
    data: dict[str, object] | None = None
    for cand in _json_candidates(text):
        try:
            obj = json.loads(cand)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict):
            data = obj
            break
    if not data:
        return None, None
    raw_it = data.get("issueType")
    it: IssueType | None = None
    if isinstance(raw_it, str) and raw_it:
        try:
            it = IssueType(raw_it)
        except ValueError:
            it = None
    ap = data.get("actionPoint")
    ap_s: str | None = None
    if isinstance(ap, str) and ap.strip():
        ap_s = re.sub(r"\s+", " ", ap.strip())[:500]
    return it, ap_s


def _llm_classify_sync(
    client: OpenAI,
    settings: Settings,
    *,
    delivery_id: str,
    transcript: str,
) -> str:
    user = json.dumps(
        {"deliveryId": delivery_id, "transcript": transcript},
        default=str,
    )
    r = client.chat.completions.create(
        model=settings.nvidia_model,
        messages=[
            {"role": "system", "content": VOICE_LLM_SYSTEM},
            {"role": "user", "content": user if len(user) < 16_000 else user[:16_000] + "…"},
        ],
        temperature=0.25,
        max_tokens=400,
        extra_body={
            "chat_template_kwargs": {"enable_thinking": False},
            "reasoning_budget": 0,
        },
    )
    return (r.choices[0].message.content or "").strip()


async def enrich_voice_callback(
    transcript: str,
    *,
    delivery_id: str,
    structured: dict | None,
    settings: Settings,
) -> VoiceEnrichment:
    """Heuristics + optional NVIDIA LLM: issue type and one operational action line."""
    base = extract_issue_type(transcript, structured=structured)
    struct = dict(structured or {})
    ap = ""
    if isinstance(struct.get("actionPoint"), str) and struct["actionPoint"].strip():
        ap = struct["actionPoint"].strip()[:500]

    client = openai_client(settings)
    if client and (transcript or "").strip():
        try:
            raw = await asyncio.to_thread(
                _llm_classify_sync,
                client,
                settings,
                delivery_id=delivery_id,
                transcript=transcript.strip(),
            )
            it, ap_llm = _parse_llm_payload(raw)
            if ap_llm:
                ap = ap_llm
            if it is not None and base.method != "structured":
                base = IssueExtraction(issue_type=it, confidence=0.88, method="llm")
        except Exception:
            logger.exception("voice callback LLM failed for delivery_id=%s", delivery_id)

    if not ap:
        ap = default_action_point(base.issue_type)
    return VoiceEnrichment(extraction=base, action_point=ap)
