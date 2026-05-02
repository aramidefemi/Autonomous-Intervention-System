"""Cooldown window logic."""

from datetime import UTC, datetime, timedelta

from ais.planner.cooldown import is_within_cooldown


def test_no_last_plan_never_cooldown() -> None:
    now = datetime.now(UTC)
    assert is_within_cooldown(now, None, 300) is False


def test_within_window() -> None:
    now = datetime.now(UTC)
    last = now - timedelta(seconds=10)
    assert is_within_cooldown(now, last, 300) is True


def test_after_window() -> None:
    now = datetime.now(UTC)
    last = now - timedelta(seconds=400)
    assert is_within_cooldown(now, last, 300) is False


def test_zero_cooldown_disabled() -> None:
    now = datetime.now(UTC)
    last = now - timedelta(seconds=1)
    assert is_within_cooldown(now, last, 0) is False
