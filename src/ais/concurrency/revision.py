"""Pure helpers for delivery revision (optimistic locking)."""


def revision_after_write(previous: int) -> int:
    """Monotonic revision after one successful delivery-document write."""
    return previous + 1


def expected_revision_allows_ingest(
    *,
    expected: int | None,
    current_revision: int | None,
) -> bool:
    """
    If the client omits X-Expected-Delivery-Revision, allow.
    If a delivery row exists, `expected` must equal current_revision.
    If no row exists, only expected 0 or None is accepted when expected is set to 0.
    """
    if expected is None:
        return True
    cur = 0 if current_revision is None else current_revision
    return expected == cur
