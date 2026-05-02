from contextlib import asynccontextmanager

from fastapi import FastAPI
from motor.motor_asyncio import AsyncIOMotorClient

from ais.config import Settings
from ais.llm import watchtower_evaluator_from_settings
from ais.logging_config import CorrelationIdMiddleware, configure_logging
from ais.repositories import EventRepository, MongoEventRepository
from ais.routes import events as events_routes
from ais.routes import health as health_routes
from ais.routes import voice as voice_routes
from ais.sqs.client import SqsClient


def create_app(
    settings: Settings | None = None,
    *,
    event_repository: EventRepository | None = None,
) -> FastAPI:
    s = settings or Settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        configure_logging()
        app.state.queue_ingress = bool(s.queue_ingress)
        app.state.sqs_client = None
        if s.queue_ingress:
            sc = SqsClient(s)
            await sc.ensure_queue_urls()
            app.state.sqs_client = sc
        if event_repository is not None:
            app.state.event_repository = event_repository
            app.state.mongo_client = None
            await event_repository.ensure_indexes()
        else:
            client = AsyncIOMotorClient(s.mongo_uri)
            app.state.mongo_client = client
            repo = MongoEventRepository(client[s.mongo_database])
            app.state.event_repository = repo
            await repo.ensure_indexes()
        app.state.watchtower_evaluator = watchtower_evaluator_from_settings(s)
        yield
        mc = getattr(app.state, "mongo_client", None)
        if mc is not None:
            mc.close()

    app = FastAPI(
        title="AI Delivery Watchtower",
        version="0.1.0",
        description="Event-driven operations API; see /docs and /redoc for OpenAPI.",
        lifespan=lifespan,
    )
    app.state.settings = s
    app.include_router(health_routes.router)
    app.include_router(events_routes.router)
    app.include_router(voice_routes.router)
    app.add_middleware(CorrelationIdMiddleware)
    return app
