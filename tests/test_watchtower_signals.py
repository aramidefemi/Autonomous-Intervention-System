from datetime import UTC, datetime, timedelta

import pytest

from ais.models import Delivery
from ais.watchtower.signals import compute_signals


@pytest.mark.parametrize(
    ("last_upd", "now", "expected_stale"),
    [
        (
            datetime(2025, 1, 1, 12, 0, 0, tzinfo=UTC),
            datetime(2025, 1, 1, 12, 4, 0, tzinfo=UTC),
            240.0,
        ),
        (
            datetime(2025, 1, 1, 12, 0, 0, tzinfo=UTC),
            datetime(2025, 1, 1, 12, 0, 0, tzinfo=UTC),
            0.0,
        ),
    ],
)
def test_staleness_seconds(
    last_upd: datetime,
    now: datetime,
    expected_stale: float,
) -> None:
    d = Delivery(
        deliveryId="D1",
        status="x",
        lastUpdatedAt=last_upd,
    )
    s = compute_signals(d, [], now=now)
    assert s.staleness_seconds == pytest.approx(expected_stale)
    assert s.eta_delta_minutes is None


def test_eta_delta_from_event_payloads() -> None:
    t0 = datetime(2025, 1, 1, 12, 0, 0, tzinfo=UTC)
    d = Delivery(deliveryId="D1", status="x", lastUpdatedAt=t0 + timedelta(minutes=10))
    events = [
        {"payload": {"etaMinutes": 15}},
        {"payload": {"etaMinutes": 40}},
    ]
    s = compute_signals(d, events, now=t0 + timedelta(hours=1))
    assert s.eta_delta_minutes == pytest.approx(25.0)


def test_no_eta_delta_with_single_reading() -> None:
    t0 = datetime(2025, 1, 1, 12, 0, 0, tzinfo=UTC)
    d = Delivery(deliveryId="D1", status="x", lastUpdatedAt=t0)
    s = compute_signals(d, [{"payload": {"etaMinutes": 20}}], now=t0)
    assert s.eta_delta_minutes is None
