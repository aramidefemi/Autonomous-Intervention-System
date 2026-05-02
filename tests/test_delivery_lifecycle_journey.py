"""E2E-style journey: webhook sequence kitchen → pickup → customer leg → voice callback.

These tests use **in-process ASGI** (``httpx.ASGITransport``) — they exercise the same Python code
as Uvicorn but do **not** open HTTP to ``docker compose``; that terminal will only show server
logs, not pytest. To hit the **running** API, use
``tests/integration/test_live_http_journey.py`` with ``AIS_LIVE_BASE_URL`` set (see that file).

Demo (prints every request body + response JSON to the terminal)::

    AIS_DEMO_VERBOSE=1 python -m pytest tests/test_delivery_lifecycle_journey.py -s -v

``-s`` disables pytest output capture so prints are visible.

The ``test_delivery_lifecycle_then_livekit_sim_join_url`` case adds a LiveKit simulate session
after the journey (browser WebRTC join URL). Outbound PSTN/SIP is not wired in this service yet.
"""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import urljoin

import pytest
from httpx import ASGITransport, AsyncClient


def _demo_verbose() -> bool:
    return os.environ.get("AIS_DEMO_VERBOSE", "").strip().lower() in ("1", "true", "yes")


def _demo_print(section: str, method: str, path: str, *, body: Any, resp: Any) -> None:
    if not _demo_verbose():
        return
    line = "=" * 72
    print(f"\n{line}\n{section}\n{line}")
    print(f"{method} {path}")
    print("--- request body ---")
    print(json.dumps(body, indent=2, default=str, ensure_ascii=False))
    print("--- response ---")
    status = getattr(resp, "status_code", None)
    if status is not None:
        print(f"HTTP {status}")
    try:
        print(json.dumps(resp.json(), indent=2, default=str, ensure_ascii=False))
    except Exception:
        print(getattr(resp, "text", resp))


def _demo_print_join_url(client_base: str, session_json: dict[str, Any]) -> None:
    """One-line URL for humans: paste into a browser when the API is running with real LiveKit."""
    if not _demo_verbose():
        return
    base = str(client_base).rstrip("/")
    join = session_json.get("joinPageUrl", "")
    full = join if str(join).startswith("http") else urljoin(base + "/", str(join).lstrip("/"))
    line = "=" * 72
    print(f"\n{line}\nJOIN THE LIVEKIT SESSION (browser) — copy this URL\n{line}\n{full}\n")


def full_delivery_journey_payloads(
    delivery_id: str,
    *,
    base_time: datetime,
) -> list[dict[str, Any]]:
    """
    Happy-path timeline. Omits etaMinutes on the pre-pickup leg so watchtower eta_delta
    stays small (rules use first/last eta across the whole event list).
    """
    def at(i: int) -> str:
        return (base_time + timedelta(seconds=i)).isoformat()

    return [
        {
            "deliveryId": delivery_id,
            "eventType": "kitchen_intent",
            "schemaVersion": 1,
            "occurredAt": at(0),
            "payload": {"status": "preparing", "station": "kitchen"},
        },
        {
            "deliveryId": delivery_id,
            "eventType": "rider_assigned",
            "schemaVersion": 1,
            "occurredAt": at(1),
            "payload": {"status": "assigned", "riderId": "R-100"},
        },
        {
            "deliveryId": delivery_id,
            "eventType": "rider_to_pickup",
            "schemaVersion": 1,
            "occurredAt": at(2),
            "payload": {"status": "en_route_pickup"},
        },
        {
            "deliveryId": delivery_id,
            "eventType": "pickup_complete",
            "schemaVersion": 1,
            "occurredAt": at(3),
            "payload": {"status": "picked_up", "etaMinutes": 20},
        },
        {
            "deliveryId": delivery_id,
            "eventType": "en_route_customer",
            "schemaVersion": 1,
            "occurredAt": at(4),
            "payload": {"status": "in_transit", "etaMinutes": 20},
        },
        {
            "deliveryId": delivery_id,
            "eventType": "approaching_dropoff",
            "schemaVersion": 1,
            "occurredAt": at(5),
            "payload": {"status": "approaching", "etaMinutes": 21},
        },
    ]


EVENT_STEP_LABELS = [
    "Webhook 1/6 — Kitchen intent (order in prep)",
    "Webhook 2/6 — Rider assigned",
    "Webhook 3/6 — Rider heading to pickup",
    "Webhook 4/6 — Picked up from vendor",
    "Webhook 5/6 — En route to customer",
    "Webhook 6/6 — Approaching dropoff",
]


@pytest.mark.asyncio
async def test_delivery_lifecycle_webhooks_then_customer_voice_callback(app) -> None:
    """Simulates multiple /v1/events calls + /v1/voice/callback (proactive customer update)."""
    did = "D-journey-e2e"
    base = datetime.now(UTC)
    payloads = full_delivery_journey_payloads(did, base_time=base)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        for i, body in enumerate(payloads):
            hdr = {"Idempotency-Key": f"{did}-step-{i}"}
            r = await client.post("/v1/events", json=body, headers=hdr)
            _demo_print(
                EVENT_STEP_LABELS[i],
                "POST",
                "/v1/events",
                body={**body, "_idempotencyKey": hdr["Idempotency-Key"]},
                resp=r,
            )
            assert r.status_code == 200, r.text
            assert r.json()["accepted"] is True

        voice_body = {
            "deliveryId": did,
            "roomName": "room-customer-update",
            "transcript": (
                "Hi, this is your rider — I'm two minutes away, ringing your bell shortly."
            ),
            "sessionEvent": "session_ended",
        }
        r = await client.post("/v1/voice/callback", json=voice_body)
        _demo_print(
            "Voice callback — Rider ↔ Customer session ended (simulated)",
            "POST",
            "/v1/voice/callback",
            body=voice_body,
            resp=r,
        )
        assert r.status_code == 200, r.text
        cb = r.json()
        assert cb["accepted"] is True

        g = await client.get(f"/v1/deliveries/{did}")
        _demo_print(
            "Read back — Full delivery + events + decisions + voice",
            "GET",
            f"/v1/deliveries/{did}",
            body={},
            resp=g,
        )
        assert g.status_code == 200
        detail = g.json()

    assert len(detail["events"]) == len(payloads)
    assert detail["delivery"]["status"] == "approaching"
    assert detail["delivery"]["deliveryId"] == did

    assert len(detail["watchtowerDecisions"]) == len(payloads)
    assert all(d["risk"] == "low" for d in detail["watchtowerDecisions"])
    assert all(d["action"] == "none" for d in detail["watchtowerDecisions"])

    # No planner actions on all-low watchtower path
    assert detail["interventionPlans"] == []

    assert len(detail["voiceOutcomes"]) == 1
    vo = detail["voiceOutcomes"][0]
    assert vo["issue_type"] == "other"
    assert "two minutes" in vo["transcript"].lower()


@pytest.mark.asyncio
async def test_delivery_lifecycle_then_livekit_sim_join_url(app_livekit) -> None:
    """After the happy-path webhooks, start a LiveKit sim session (ops opening + room token)."""
    did = "D-journey-livekit"
    base = datetime.now(UTC)
    payloads = full_delivery_journey_payloads(did, base_time=base)

    transport = ASGITransport(app=app_livekit)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        for i, body in enumerate(payloads):
            hdr = {"Idempotency-Key": f"{did}-lk-step-{i}"}
            r = await client.post("/v1/events", json=body, headers=hdr)
            _demo_print(
                EVENT_STEP_LABELS[i],
                "POST",
                "/v1/events",
                body={**body, "_idempotencyKey": hdr["Idempotency-Key"]},
                resp=r,
            )
            assert r.status_code == 200, r.text

        r = await client.post("/v1/voice/simulate/session", json={"deliveryId": did})
        j = r.json() if r.status_code == 200 else {}
        _demo_print(
            "LiveKit simulate session — room + join page (agent would connect here / bridge PSTN later)",
            "POST",
            "/v1/voice/simulate/session",
            body={"deliveryId": did},
            resp=r,
        )
        _demo_print_join_url(str(client.base_url), j)
        assert r.status_code == 200, r.text
        assert j["livekitUrl"] == "wss://example.livekit.cloud"
        assert j["roomName"].startswith("wt-")
        assert j["joinPageUrl"]
        assert j["identity"] == "sim-D-journey-livekit"
