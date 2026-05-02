from ais.concurrency.revision import (
    expected_revision_allows_ingest,
    revision_after_write,
)


def test_revision_after_write() -> None:
    assert revision_after_write(0) == 1
    assert revision_after_write(3) == 4


def test_expected_revision_omit_always_ok() -> None:
    assert expected_revision_allows_ingest(expected=None, current_revision=None)
    assert expected_revision_allows_ingest(expected=None, current_revision=5)


def test_expected_matches_missing_delivery() -> None:
    assert expected_revision_allows_ingest(expected=0, current_revision=None)
    assert not expected_revision_allows_ingest(expected=1, current_revision=None)


def test_expected_matches_existing() -> None:
    assert expected_revision_allows_ingest(expected=2, current_revision=2)
    assert not expected_revision_allows_ingest(expected=1, current_revision=2)
