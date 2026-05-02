"""Live HTTP chaos journey: escalates ETA slip → stale signal; prints which “nodes” ran.

After each ``POST /v1/events`` the test **GET**s ``/v1/deliveries/{id}`` and prints the latest
watchtower row (``source`` = ``rules`` or ``llm`` — Watchtower evaluator) and any new intervention
plan (planner is always **rules** policy in code). Optional voice + sim opening show **ops opening**
(``llm`` / ``rules``) and voice extraction.

Run (API up, e.g. ``docker compose up``)::

    AIS_LIVE_BASE_URL=http://127.0.0.1:8000 \\
      AIS_DEMO_VERBOSE=1 \\
      python -m pytest tests/integration/test_live_chaos_narrative.py -m integration -s -v

With ``NVIDIA_API_KEY`` on the server, watchtower decisions typically show ``source=llm``; otherwise
``rules``. Planner cooldown may suppress extra intervention rows after the first non-low risk.
"""

from __future__ import annotations

import json
import os
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import pytest


def _chaos_verbose() -> bool:
    v = os.environ.get("AIS_CHAOS_VERBOSE", "").strip().lower()
    d = os.environ.get("AIS_DEMO_VERBOSE", "").strip().lower()
    return v in ("1", "true", "yes") or d in ("1", "true", "yes")


def _live_base_url() -> str | None:
    u = os.environ.get("AIS_LIVE_BASE_URL", "").strip()
    return u or None


def _g(d: dict[str, Any], *keys: str) -> Any:
    for k in keys:
        if k in d:
            return d[k]
    return None


def chaos_payloads(delivery_id: str, *, base: datetime) -> list[tuple[str, dict[str, Any]]]:
    """(human label, event json). Timestamps drive staleness and ETA delta deterministically."""

    def at(sec: float) -> str:
        return (base + timedelta(seconds=sec)).isoformat()

    stale = (base - timedelta(seconds=450)).isoformat()

    return [
        (
            "1/8 — Kitchen starts prep",
            {
                "deliveryId": delivery_id,
                "eventType": "kitchen_intent",
                "schemaVersion": 1,
                "occurredAt": at(0),
                "payload": {"status": "preparing", "station": "kitchen"},
            },
        ),
        (
            "2/8 — Rider assigned",
            {
                "deliveryId": delivery_id,
                "eventType": "rider_assigned",
                "schemaVersion": 1,
                "occurredAt": at(1),
                "payload": {"status": "assigned", "riderId": "R-chaos"},
            },
        ),
        (
            "3/8 — Rider en route to pickup",
            {
                "deliveryId": delivery_id,
                "eventType": "rider_to_pickup",
                "schemaVersion": 1,
                "occurredAt": at(2),
                "payload": {"status": "en_route_pickup"},
            },
        ),
        (
            "4/8 — Picked up; ETA looks fine",
            {
                "deliveryId": delivery_id,
                "eventType": "pickup_complete",
                "schemaVersion": 1,
                "occurredAt": at(3),
                "payload": {"status": "picked_up", "etaMinutes": 12},
            },
        ),
        (
            "5/8 — Chaos: ETA stretches (slip > 10 min vs first ETA)",
            {
                "deliveryId": delivery_id,
                "eventType": "en_route_customer",
                "schemaVersion": 1,
                "occurredAt": at(4),
                "payload": {"status": "in_transit", "etaMinutes": 38},
            },
        ),
        (
            "6/8 — Still blown ETA approaching dropoff",
            {
                "deliveryId": delivery_id,
                "eventType": "approaching_dropoff",
                "schemaVersion": 1,
                "occurredAt": at(5),
                "payload": {"status": "approaching", "etaMinutes": 40},
            },
        ),
        (
            "7/8 — Ghost telemetry: occurredAt far in the past → staleness rule",
            {
                "deliveryId": delivery_id,
                "eventType": "location_update",
                "schemaVersion": 1,
                "occurredAt": stale,
                "payload": {"status": "in_transit", "lastLatLngAgeSeconds": 9999},
            },
        ),
        (
            "8/8 — Voice leg: rider reports traffic (callback)",
            {
                "_voice_callback": True,
            },
        ),
    ]


def _print_pipeline_banner(title: str) -> None:
    if not _chaos_verbose():
        return
    line = "=" * 72
    print(f"\n{line}\n{title}\n{line}")


def _print_after_event(
    *,
    step_label: str,
    ingest: dict[str, Any],
    detail: dict[str, Any],
) -> None:
    if not _chaos_verbose():
        return
    line = "-" * 72
    print(f"\n{line}\n{step_label}\n{line}")
    print(f"POST /v1/events → traceId={ingest.get('traceId')} accepted={ingest.get('accepted')}")
    print(
        "\n• Pipeline (server): ingest → run_watchtower(evaluator) → "
        "run_intervention_planner(rules policy)"
    )
    wt = _g(detail, "watchtowerDecisions") or []
    plans = _g(detail, "interventionPlans") or []
    if isinstance(wt, list) and wt:
        w0 = wt[0]
        src = _g(w0, "source") or "?"
        risk = _g(w0, "risk") or "?"
        reason = _g(w0, "reason") or "?"
        sig = _g(w0, "signals") or {}
        node = "Watchtower [LLM]" if src == "llm" else "Watchtower [rules]"
        print(f"\n• {node}  (source={src})")
        print(f"  risk={risk}  reason={reason}")
        print(f"  signals={json.dumps(sig, default=str)}")
    if isinstance(plans, list) and plans:
        p0 = plans[0]
        it = _g(p0, "interventionType", "intervention_type") or "?"
        pr = _g(p0, "reason") or "?"
        psrc = _g(p0, "source") or "rules"
        print(f"\n• Intervention planner [rules]  (source={psrc})")
        print(f"  interventionType={it}  reason={pr}")
        if len(plans) > 1:
            print(f"  (history: {len(plans)} plans total; showing latest)")
    else:
        print(
            "\n• Intervention planner: no plan "
            "(nominal or cooldown — see INTERVENTION_COOLDOWN_SECONDS on server)"
        )


def _print_voice_opening(j: dict[str, Any]) -> None:
    if not _chaos_verbose():
        return
    src = j.get("openingSource", "?")
    node = "Ops opening [LLM]" if src == "llm" else "Ops opening [rules]"
    print(f"\n• {node}  openingSource={src}")
    print(f"  line={j.get('openingLine', '')[:200]}")


@pytest.mark.integration
@pytest.mark.asyncio
async def test_live_chaos_narrative_with_ai_trace() -> None:
    base_url = _live_base_url()
    if not base_url:
        pytest.skip("Set AIS_LIVE_BASE_URL=http://127.0.0.1:8000")

    did = f"D-chaos-{uuid.uuid4().hex[:10]}"
    t0 = datetime.now(UTC)
    steps = chaos_payloads(did, base=t0)
    root = base_url.rstrip("/")

    timeout = httpx.Timeout(120.0, connect=5.0)
    async with httpx.AsyncClient(base_url=root, timeout=timeout) as client:
        try:
            h = await client.get("/health")
        except httpx.ConnectError as e:
            pytest.skip(f"API not reachable at {root}: {e}")
        if h.status_code != 200:
            pytest.skip(f"GET /health → {h.status_code}")

        _print_pipeline_banner(f"CHAOS NARRATIVE  deliveryId={did}")

        for i, (label, body) in enumerate(steps):
            if body.get("_voice_callback"):
                voice_body = {
                    "deliveryId": did,
                    "roomName": f"room-chaos-{did}",
                    "transcript": (
                        "I'm stuck in heavy traffic on the bridge, maybe fifteen minutes late."
                    ),
                    "sessionEvent": "session_ended",
                    "source": "livekit_webhook",
                }
                rv = await client.post("/v1/voice/callback", json=voice_body)
                if _chaos_verbose():
                    print(f"\n{'-' * 72}\n{label}\n{'-' * 72}")
                    print("POST /v1/voice/callback → voice extraction + Mongo outcome")
                    try:
                        print(json.dumps(rv.json(), indent=2, default=str))
                    except Exception:
                        print(rv.text)
                assert rv.status_code == 200, rv.text
                det = (await client.get(f"/v1/deliveries/{did}")).json()
                vo = _g(det, "voiceOutcomes") or []
                if _chaos_verbose() and isinstance(vo, list) and vo:
                    v0 = vo[0]
                    print(
                        "\n• Voice issue classifier [heuristics/llm in app]\n"
                        f"  issueType={_g(v0, 'issueType', 'issue_type')} "
                        f"method={_g(v0, 'extractionMethod', 'extraction_method')}"
                    )
                continue

            hdr = {"Idempotency-Key": f"{did}-chaos-{i}"}
            r = await client.post("/v1/events", json=body, headers=hdr)
            assert r.status_code == 200, r.text
            ing = r.json()
            assert ing.get("accepted") is True
            detail = (await client.get(f"/v1/deliveries/{did}")).json()
            _print_after_event(step_label=label, ingest=ing, detail=detail)

        det = (await client.get(f"/v1/deliveries/{did}")).json()
        wt = _g(det, "watchtowerDecisions") or []
        assert isinstance(wt, list) and len(wt) >= 7

        risks = {str(_g(x, "risk") or "") for x in wt}
        assert "medium" in risks, "expected ETA slip to surface as medium (rules) or LLM medium"
        assert "high" in risks, "expected stale telemetry to surface as high (rules) or LLM high"

        op = await client.get(f"/v1/voice/simulate/opening/{did}")
        if op.status_code == 200:
            _print_voice_opening(op.json())

        rs = await client.post("/v1/voice/simulate/session", json={"deliveryId": did})
        if rs.status_code == 200 and _chaos_verbose():
            sj = rs.json()
            print(f"\n{'=' * 72}\nLiveKit sim session (optional)\n{'=' * 72}")
            print(f"joinPageUrl={sj.get('joinPageUrl')}")
            src = sj.get("openingSource", "?")
            print(f"openingSource={src} ({'LLM' if src == 'llm' else 'rules'})")

        if _chaos_verbose():
            print(f"\n{'=' * 72}\nFINAL SNAPSHOT  trace summary\n{'=' * 72}")
            print(f"watchtowerDecisions: {len(wt)}")
            print(f"interventionPlans: {len(_g(det, 'interventionPlans') or [])}")
            print(f"voiceOutcomes: {len(_g(det, 'voiceOutcomes') or [])}")
