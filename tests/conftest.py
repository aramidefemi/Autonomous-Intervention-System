import pytest
from asgi_lifespan import LifespanManager

from ais.app import create_app
from ais.config import Settings
from tests.fakes import InMemoryEventRepository


@pytest.fixture
def test_settings() -> Settings:
    return Settings(
        mongo_uri="mongodb://localhost:27017",
        aws_endpoint_url=None,
        queue_ingress=False,
        livekit_url=None,
        livekit_api_key=None,
        livekit_api_secret=None,
        nvidia_api_key=None,
    )


@pytest.fixture
async def app(test_settings: Settings):
    application = create_app(test_settings, event_repository=InMemoryEventRepository())
    async with LifespanManager(application):
        yield application


@pytest.fixture
async def app_livekit(test_settings: Settings):
    """ASGI app with LiveKit env set so /v1/voice/simulate/* works (JWT is real; URL is a stub)."""
    s = test_settings.model_copy(
        update={
            "livekit_url": "wss://example.livekit.cloud",
            "livekit_api_key": "test_key",
            "livekit_api_secret": "test_secret",
        }
    )
    application = create_app(s, event_repository=InMemoryEventRepository())
    async with LifespanManager(application):
        yield application
