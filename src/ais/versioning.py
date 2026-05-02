"""Single source of truth for event schema versions."""

SUPPORTED_EVENT_SCHEMA_VERSIONS: frozenset[int] = frozenset({1})


def assert_supported_schema_version(version: int) -> None:
    if version not in SUPPORTED_EVENT_SCHEMA_VERSIONS:
        supported = sorted(SUPPORTED_EVENT_SCHEMA_VERSIONS)
        msg = f"Unsupported schemaVersion {version}; supported: {supported}"
        raise ValueError(msg)


def current_event_schema_version() -> int:
    return max(SUPPORTED_EVENT_SCHEMA_VERSIONS)
