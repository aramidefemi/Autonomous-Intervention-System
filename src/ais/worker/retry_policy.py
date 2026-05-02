"""Pure backoff for transient worker failures (visibility extension)."""


def visibility_delay_seconds(*, attempt: int, base_seconds: int = 2, cap_seconds: int = 900) -> int:
    """attempt is 1-based receive count after first failure (use receive_count from SQS)."""
    if attempt < 1:
        attempt = 1
    # exponential: base * 2^(attempt-1), capped
    exp = min(cap_seconds, base_seconds * (2 ** (attempt - 1)))
    return max(1, int(exp))
