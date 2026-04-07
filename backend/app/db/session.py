from collections.abc import Generator
from typing import Any

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import get_settings

settings = get_settings()


def _get_engine_kwargs() -> dict[str, Any]:
    engine_kwargs: dict[str, Any] = {
        "future": True,
        "pool_pre_ping": True,
        "echo": settings.database_echo,
    }
    if settings.database_url.startswith("postgresql"):
        engine_kwargs["pool_size"] = settings.database_pool_size
        engine_kwargs["max_overflow"] = settings.database_max_overflow
    return engine_kwargs


engine = create_engine(settings.database_url, **_get_engine_kwargs())
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, class_=Session)


def get_db_session() -> Generator[Session, None, None]:
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
