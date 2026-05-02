import pytest

from ais.versioning import (
    assert_supported_schema_version,
    current_event_schema_version,
)


def test_current_version_in_supported_set() -> None:
    v = current_event_schema_version()
    assert_supported_schema_version(v)


def test_rejects_unknown_version() -> None:
    with pytest.raises(ValueError, match="Unsupported schemaVersion"):
        assert_supported_schema_version(0)
