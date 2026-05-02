"""Scriptable bike-breakdown scenario for demos and integration smoke tests."""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx


def bike_breakdown_payloads(delivery_id: str = "D-demo-bike") -> list[dict[str, Any]]:
    # occurredAt is stale (16 min ago) so watchtower detects staleness on every event.
    # Two eta_* events give compute_signals a baseline (10 min) and a slipped value (28 min),
    # producing etaDeltaMinutes = +18 which exceeds the ETA_SLIP_MINUTES=10 threshold.
    old = (datetime.now(UTC) - timedelta(minutes=16)).isoformat()
    return [
        {
            "deliveryId": delivery_id,
            "eventType": "delivery_created",
            "schemaVersion": 1,
            "occurredAt": old,
            "payload": {"status": "in_transit", "etaMinutes": 10},
        },
        {
            "deliveryId": delivery_id,
            "eventType": "location_update",
            "schemaVersion": 1,
            "occurredAt": old,
            "payload": {"status": "in_transit"},
        },
        {
            "deliveryId": delivery_id,
            "eventType": "eta_update",
            "schemaVersion": 1,
            "occurredAt": old,
            "payload": {"status": "in_transit", "etaMinutes": 28},
        },
        {
            "deliveryId": delivery_id,
            "eventType": "rider_status",
            "schemaVersion": 1,
            "occurredAt": old,
            "payload": {"status": "delayed", "reason": "mechanical"},
        },
    ]


def voice_callback_payload(delivery_id: str = "D-demo-bike") -> dict[str, Any]:
    return {
        "deliveryId": delivery_id,
        "roomName": "demo-room",
        "transcript": "My bike broke down, I cannot continue the delivery.",
        "sessionEvent": "session_ended",
    }


async def run_bike_breakdown_demo(
    *,
    base_url: str,
    client: httpx.AsyncClient | None = None,
    delivery_id: str = "D-demo-bike",
) -> dict[str, Any]:
    """POST event sequence + voice callback; return GET /v1/deliveries/{id} body."""
    own = client is None
    c = client or httpx.AsyncClient(base_url=base_url.rstrip("/"), timeout=60.0)
    cid_hdr = os.environ.get("DEMO_CORRELATION_ID", "demo-bike-breakdown")
    headers = {"X-Correlation-ID": cid_hdr}
    try:
        for payload in bike_breakdown_payloads(delivery_id):
            r = await c.post("/v1/events", json=payload, headers=headers)
            r.raise_for_status()
        r = await c.post(
            "/v1/voice/callback",
            json=voice_callback_payload(delivery_id),
            headers=headers,
        )
        r.raise_for_status()
        g = await c.get(f"/v1/deliveries/{delivery_id}", headers=headers)
        g.raise_for_status()
        return g.json()
    finally:
        if own:
            await c.aclose()
