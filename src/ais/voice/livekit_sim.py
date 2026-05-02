"""Helpers for WebRTC simulation via LiveKit (browser join; PSTN is separate)."""

from __future__ import annotations

import re
import secrets
from dataclasses import dataclass
from datetime import timedelta


def slug_delivery_id(delivery_id: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9]+", "-", delivery_id.strip())
    s = s.strip("-")[:48]
    return s or "delivery"


def new_simulation_room_name(delivery_id: str) -> str:
    return f"wt-{slug_delivery_id(delivery_id)}-{secrets.token_hex(3)}"


@dataclass(frozen=True)
class SimulationJoin:
    room_name: str
    token: str
    identity: str


def build_simulation_join(
    *,
    api_key: str,
    api_secret: str,
    delivery_id: str,
    ttl: timedelta | None = None,
) -> SimulationJoin:
    from livekit import api

    room_name = new_simulation_room_name(delivery_id)
    identity = f"sim-{slug_delivery_id(delivery_id)}"
    td = ttl if ttl is not None else timedelta(minutes=30)
    token = (
        api.AccessToken(api_key, api_secret)
        .with_identity(identity)
        .with_name(f"Sim · {delivery_id[:64]}")
        .with_ttl(td)
        .with_grants(
            api.VideoGrants(
                room_join=True,
                room=room_name,
            )
        )
        .to_jwt()
    )
    return SimulationJoin(room_name=room_name, token=token, identity=identity)


def normalize_livekit_url(url: str) -> str:
    u = url.strip()
    if u.startswith("https://"):
        return "wss://" + u.removeprefix("https://")
    if u.startswith("http://"):
        return "ws://" + u.removeprefix("http://")
    return u
