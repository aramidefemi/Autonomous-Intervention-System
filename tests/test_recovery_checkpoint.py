"""Pure checkpoint helpers (Phase 6)."""

from datetime import UTC, datetime, timedelta

from ais.recovery.checkpoint import (
    delivery_has_stale_open_pipeline,
    migrate_delivery_checkpoint_defaults,
)


def test_migrate_defaults_fill_missing() -> None:
    raw = {"delivery_id": "D1", "status": "x"}
    out = migrate_delivery_checkpoint_defaults(raw)
    assert out["last_processed_seq"] == 0
    assert out["open_pipeline_idempotency_key"] is None
    assert out["open_intervention_id"] is None


def test_stale_when_started_old() -> None:
    now = datetime(2026, 5, 2, 12, 0, 0, tzinfo=UTC)
    started = now - timedelta(minutes=10)
    assert delivery_has_stale_open_pipeline(
        open_pipeline_idempotency_key="k",
        open_pipeline_started_at=started,
        now=now,
        stale_after_seconds=60,
    )


def test_not_stale_when_recent() -> None:
    now = datetime(2026, 5, 2, 12, 0, 0, tzinfo=UTC)
    started = now - timedelta(seconds=30)
    assert not delivery_has_stale_open_pipeline(
        open_pipeline_idempotency_key="k",
        open_pipeline_started_at=started,
        now=now,
        stale_after_seconds=60,
    )


def test_no_open_key_not_stale() -> None:
    now = datetime(2026, 5, 2, 12, 0, 0, tzinfo=UTC)
    assert not delivery_has_stale_open_pipeline(
        open_pipeline_idempotency_key=None,
        open_pipeline_started_at=None,
        now=now,
        stale_after_seconds=60,
    )


def test_missing_started_at_is_stale() -> None:
    now = datetime(2026, 5, 2, 12, 0, 0, tzinfo=UTC)
    assert delivery_has_stale_open_pipeline(
        open_pipeline_idempotency_key="k",
        open_pipeline_started_at=None,
        now=now,
        stale_after_seconds=60,
    )
