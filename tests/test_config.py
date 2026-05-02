import pytest
from pydantic import ValidationError

from ais.config import Settings


def test_rejects_invalid_port() -> None:
    with pytest.raises(ValidationError):
        Settings(mongo_uri="mongodb://x", app_port=0)
    with pytest.raises(ValidationError):
        Settings(mongo_uri="mongodb://x", app_port=70000)


def test_rejects_bad_mongo_uri() -> None:
    with pytest.raises(ValidationError):
        Settings(mongo_uri="redis://nope")
    with pytest.raises(ValidationError):
        Settings(mongo_uri="")


def test_rejects_bad_aws_endpoint() -> None:
    with pytest.raises(ValidationError):
        Settings(mongo_uri="mongodb://x", aws_endpoint_url="not-a-url")


def test_endpoint_requires_keys() -> None:
    with pytest.raises(ValidationError):
        Settings(
            mongo_uri="mongodb://x",
            aws_endpoint_url="http://localhost:4566",
            aws_access_key_id="",
            aws_secret_access_key="test",
        )


def test_strips_trailing_slash_on_endpoint() -> None:
    s = Settings(
        mongo_uri="mongodb://x",
        aws_endpoint_url="http://localhost:4566/",
    )
    assert s.aws_endpoint_url == "http://localhost:4566"


def test_queue_ingress_requires_endpoint() -> None:
    with pytest.raises(ValidationError):
        Settings(
            mongo_uri="mongodb://x",
            queue_ingress=True,
            aws_endpoint_url=None,
        )


def test_loads_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MONGO_URI", "mongodb://envhost:27017")
    monkeypatch.setenv("APP_PORT", "9000")
    s = Settings()
    assert s.mongo_uri == "mongodb://envhost:27017"
    assert s.app_port == 9000
