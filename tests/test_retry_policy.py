from ais.worker.retry_policy import visibility_delay_seconds


def test_visibility_delay_exponential_capped() -> None:
    assert visibility_delay_seconds(attempt=1, base_seconds=2, cap_seconds=900) == 2
    assert visibility_delay_seconds(attempt=2, base_seconds=2, cap_seconds=900) == 4
    assert visibility_delay_seconds(attempt=3, base_seconds=2, cap_seconds=900) == 8
    assert visibility_delay_seconds(attempt=20, base_seconds=2, cap_seconds=32) == 32
