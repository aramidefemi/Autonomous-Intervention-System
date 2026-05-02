"""HTTP integration: same journey as ``test_delivery_lifecycle_journey`` against a **running** API.

Requires Uvicorn up (e.g. ``docker compose up``) and reachable Mongo per the API's ``.env``.

Run (second terminal, while compose is up)::

    AIS_LIVE_BASE_URL=http://127.0.0.1:8000 AIS_DEMO_VERBOSE=1 \\
      python -m pytest tests/integration/test_live_http_journey.py -m integration -s -v

Default ``pytest`` excludes ``-m integration`` (see ``pyproject.toml``); you must pass ``-m integration``.
LiveKit simulate step is skipped if the server returns 503 (no ``LIVEKIT_*`` in api env).
"""

from __future__ import annotations

import os
import uuid
from datetime import UTC, datetime

import httpx
import pytest

from tests.test_delivery_lifecycle_journey import (
    EVENT_STEP_LABELS,
    _demo_print,
    _demo_print_join_url,
    full_delivery_journey_payloads,
)


def _live_base_url() -> str | None:
    u = os.environ.get("AIS_LIVE_BASE_URL", "").strip()
    return u or None


@pytest.mark.integration
@pytest.mark.asyncio
async def test_live_http_delivery_journey_and_optional_livekit_join_url() -> None:
    base_url = _live_base_url()
    if not base_url:
        pytest.skip("Set AIS_LIVE_BASE_URL=http://127.0.0.1:8000 (api must be running)")

    did = f"D-live-{uuid.uuid4().hex[:10]}"
    t0 = datetime.now(UTC)
    payloads = full_delivery_journey_payloads(did, base_time=t0)
    root = base_url.rstrip("/")

    timeout = httpx.Timeout(60.0, connect=5.0)
    async with httpx.AsyncClient(base_url=root, timeout=timeout) as client:
        try:
            h = await client.get("/health")
        except httpx.ConnectError as e:
            pytest.skip(f"API not reachable at {root}: {e}")
        if h.status_code != 200:
            pytest.skip(f"GET /health expected 200, got {h.status_code}")

        for i, body in enumerate(payloads):
            hdr = {"Idempotency-Key": f"{did}-live-{i}"}
            r = await client.post("/v1/events", json=body, headers=hdr)
            _demo_print(
                EVENT_STEP_LABELS[i],
                "POST",
                "/v1/events",
                body={**body, "_idempotencyKey": hdr["Idempotency-Key"]},
                resp=r,
            )
            assert r.status_code == 200, r.text
            assert r.json().get("accepted") is True

        r = await client.post("/v1/voice/simulate/session", json={"deliveryId": did})
        j = r.json() if r.content else {}
        _demo_print(
            "POST /v1/voice/simulate/session (real server; needs LIVEKIT_* for 200)",
            "POST",
            "/v1/voice/simulate/session",
            body={"deliveryId": did},
            resp=r,
        )
        if r.status_code == 503:
            pytest.skip("Server: LiveKit not configured (set LIVEKIT_URL, LIVEKIT_API_KEY, LIVEKIT_API_SECRET for api)")
        assert r.status_code == 200, r.text
        _demo_print_join_url(root, j)
        assert j.get("joinPageUrl")
        assert j.get("roomName")
