from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.config import get_settings
from app.db.init import init_db
from app.jobs.scheduler import start_scheduler, stop_scheduler


def _configure_logging(level_name: str) -> None:
    """Configure basic application logging with env-driven log level."""
    level = getattr(logging, level_name.upper(), logging.INFO)
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )


@asynccontextmanager
async def app_lifespan(_: FastAPI) -> AsyncGenerator[None, None]:
    settings = get_settings()
    settings.validate_startup_settings()
    init_db()
    start_scheduler(settings)
    yield
    stop_scheduler()


def create_app() -> FastAPI:
    settings = get_settings()
    _configure_logging(settings.log_level)
    app = FastAPI(title=settings.app_name, lifespan=app_lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[origin.strip() for origin in settings.cors_origins.split(",") if origin.strip()],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(api_router)
    return app


app = create_app()
