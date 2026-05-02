"""Pure cooldown: avoid duplicate plans within a time window."""

from datetime import UTC, datetime


def _utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def is_within_cooldown(
    now: datetime,
    last_planned_at: datetime | None,
    cooldown_seconds: int,
) -> bool:
    if last_planned_at is None or cooldown_seconds <= 0:
        return False
    delta = (_utc(now) - _utc(last_planned_at)).total_seconds()
    return delta < cooldown_seconds
