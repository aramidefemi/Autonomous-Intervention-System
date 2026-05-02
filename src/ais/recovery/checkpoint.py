"""Pure helpers for pipeline checkpoint migration and stale-open classification."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any


def migrate_delivery_checkpoint_defaults(raw: dict[str, Any]) -> dict[str, Any]:
    """Fill Phase 6 checkpoint defaults for legacy delivery documents."""
    out = dict(raw)
    out.setdefault("last_processed_seq", 0)
    out.setdefault("open_pipeline_idempotency_key", None)
    out.setdefault("open_pipeline_started_at", None)
    out.setdefault("open_intervention_id", None)
    return out


def delivery_has_stale_open_pipeline(
    *,
    open_pipeline_idempotency_key: str | None,
    open_pipeline_started_at: datetime | None,
    now: datetime,
    stale_after_seconds: int,
) -> bool:
    """True when an open pipeline should be treated as stale for recovery scans."""
    if not open_pipeline_idempotency_key:
        return False
    if open_pipeline_started_at is None:
        return True
    cutoff = now - timedelta(seconds=stale_after_seconds)
    return open_pipeline_started_at < cutoff
