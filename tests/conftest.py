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
    )


@pytest.fixture
async def app(test_settings: Settings):
    application = create_app(test_settings, event_repository=InMemoryEventRepository())
    async with LifespanManager(application):
        yield application
