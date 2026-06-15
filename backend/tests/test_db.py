from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, text
from sqlalchemy.engine import URL
from sqlalchemy.pool import StaticPool

import app.db.init as db_init_module
from app.config import Settings, get_settings
from app.db.base import Base
from app.db.init import init_db
from app.db.session import create_database_engine


def _sqlite_url(database_path: Path) -> str:
    return URL.create(
        drivername="sqlite+pysqlite",
        database=str(database_path),
    ).render_as_string(hide_password=False)


def test_all_mvp_tables_registered() -> None:
    table_names = set(Base.metadata.tables.keys())
    assert {
        "issues",
        "issue_history",
        "releases",
        "metric_snapshots",
        "release_signals",
    }.issubset(table_names)


def test_init_db_calls_create_all(monkeypatch) -> None:
    called = {"value": False}

    def _fake_create_all(*args, **kwargs) -> None:
        called["value"] = True

    monkeypatch.setattr(Base.metadata, "create_all", _fake_create_all)
    init_db(ensure_compat_columns=False)

    assert called["value"] is True


def test_init_db_compat_columns_include_release_scope_counts(monkeypatch) -> None:
    statements: list[str] = []

    class FakeDialect:
        name = "postgresql"

    class FakeConnection:
        def execute(self, statement) -> None:
            statements.append(str(statement))

    class FakeBegin:
        def __enter__(self) -> FakeConnection:
            return FakeConnection()

        def __exit__(self, exc_type, exc, traceback) -> None:
            return None

    class FakeEngine:
        dialect = FakeDialect()

        def begin(self) -> FakeBegin:
            return FakeBegin()

    monkeypatch.setattr(db_init_module, "engine", FakeEngine())
    monkeypatch.setattr(Base.metadata, "create_all", lambda *args, **kwargs: None)

    init_db()

    assert any("scope_added_7d_count INTEGER NOT NULL DEFAULT 0" in statement for statement in statements)
    assert any("scope_removed_7d_count INTEGER NOT NULL DEFAULT 0" in statement for statement in statements)


def test_create_database_engine_supports_file_backed_sqlite(tmp_path: Path) -> None:
    database_path = tmp_path / "nested" / "lighthouse.db"
    database_engine = create_database_engine(Settings(_env_file=None, database_url=_sqlite_url(database_path)))

    try:
        with database_engine.connect() as connection:
            foreign_keys_enabled = connection.scalar(text("PRAGMA foreign_keys"))
            busy_timeout = connection.scalar(text("PRAGMA busy_timeout"))
            journal_mode = connection.scalar(text("PRAGMA journal_mode"))
    finally:
        database_engine.dispose()

    assert database_path.exists()
    assert foreign_keys_enabled == 1
    assert busy_timeout == 30000
    assert journal_mode == "wal"


def test_create_database_engine_uses_static_pool_for_in_memory_sqlite() -> None:
    database_engine = create_database_engine(Settings(_env_file=None, database_url="sqlite+pysqlite:///:memory:"))

    try:
        assert isinstance(database_engine.pool, StaticPool)
    finally:
        database_engine.dispose()


def test_alembic_upgrade_head_supports_sqlite(tmp_path: Path, monkeypatch) -> None:
    database_path = tmp_path / "migrated.db"
    database_url = _sqlite_url(database_path)
    alembic_config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))

    monkeypatch.setenv("DATABASE_URL", database_url)
    get_settings.cache_clear()
    try:
        command.upgrade(alembic_config, "head")
    finally:
        get_settings.cache_clear()

    database_engine = create_database_engine(Settings(_env_file=None, database_url=database_url))
    try:
        schema = inspect(database_engine)
        table_names = set(schema.get_table_names())
        metric_columns = {column["name"] for column in schema.get_columns("metric_snapshots")}
        sprint_metric_columns = {column["name"] for column in schema.get_columns("sprint_metric_snapshots")}
    finally:
        database_engine.dispose()

    assert {
        "alembic_version",
        "issue_history",
        "issue_sprints",
        "issues",
        "metric_snapshots",
        "release_signals",
        "releases",
        "sprint_metric_snapshots",
        "sprints",
    }.issubset(table_names)
    assert {
        "completed_tickets",
        "open_blocker_issue_keys",
        "open_high_severity_bug_issue_keys",
        "scope_added_7d_count",
        "scope_removed_7d_count",
    }.issubset(metric_columns)
    assert {
        "bugs_created_during_sprint",
        "bugs_created_during_sprint_issue_keys",
        "delivery_confidence_components",
        "delivery_confidence_inputs",
        "delivery_confidence_score",
    }.issubset(sprint_metric_columns)
