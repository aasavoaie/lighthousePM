from collections.abc import Generator
from pathlib import Path
from typing import Any

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.config import Settings, get_settings

settings = get_settings()


def _ensure_sqlite_parent_directory(database_url: str) -> None:
    url = make_url(database_url)
    if url.get_backend_name() != "sqlite":
        return

    database_path = url.database
    if not database_path or database_path == ":memory:" or database_path.startswith("file:"):
        return

    Path(database_path).expanduser().parent.mkdir(parents=True, exist_ok=True)


def _enable_sqlite_foreign_keys(engine: Engine) -> None:
    @event.listens_for(engine, "connect")
    def _set_sqlite_pragma(dbapi_connection: Any, _: Any) -> None:
        cursor = dbapi_connection.cursor()
        try:
            cursor.execute("PRAGMA busy_timeout=30000")
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA foreign_keys=ON")
        finally:
            cursor.close()


def _get_engine_kwargs(database_settings: Settings) -> dict[str, Any]:
    engine_kwargs: dict[str, Any] = {
        "future": True,
        "pool_pre_ping": True,
        "echo": database_settings.database_echo,
    }
    effective_database_url = database_settings.effective_database_url
    backend_name = make_url(effective_database_url).get_backend_name()
    if backend_name == "postgresql":
        engine_kwargs["pool_size"] = database_settings.database_pool_size
        engine_kwargs["max_overflow"] = database_settings.database_max_overflow
    elif backend_name == "sqlite":
        engine_kwargs["connect_args"] = {
            "check_same_thread": False,
            "timeout": 30.0,
        }
        if make_url(effective_database_url).database == ":memory:":
            engine_kwargs["poolclass"] = StaticPool
    return engine_kwargs


def create_database_engine(database_settings: Settings) -> Engine:
    """Create a configured PostgreSQL or SQLite SQLAlchemy engine."""
    effective_database_url = database_settings.effective_database_url
    _ensure_sqlite_parent_directory(effective_database_url)
    database_engine = create_engine(
        effective_database_url,
        **_get_engine_kwargs(database_settings),
    )
    if database_engine.dialect.name == "sqlite":
        _enable_sqlite_foreign_keys(database_engine)
    return database_engine


engine = create_database_engine(settings)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, class_=Session)


def get_db_session() -> Generator[Session, None, None]:
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
