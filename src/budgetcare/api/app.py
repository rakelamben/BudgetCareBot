from contextlib import asynccontextmanager

from fastapi import FastAPI

from budgetcare.api.routes import dashboard, health, telegram, tick
from budgetcare.config import settings
from budgetcare.logging import logger, setup_logging


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging(settings.LOG_LEVEL)
    logger.info("app_starting", app_env=settings.APP_ENV)
    yield
    logger.info("app_stopping")


def create_app() -> FastAPI:
    app = FastAPI(
        title="Budget Care API",
        version="0.1.0",
        lifespan=lifespan,
    )

    app.include_router(health.router)
    app.include_router(telegram.router)
    app.include_router(tick.router)
    app.include_router(dashboard.router)

    return app
