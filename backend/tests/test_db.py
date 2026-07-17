from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, text
from sqlalchemy.engine import URL
from sqlalchemy.pool import StaticPool
import pytest

import app.db.init as db_init_module
from app.config import Settings
from app.db.base import Base
from app.db.init import init_db
from app.db.migrations import migrate_database
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
    init_db(ensure_compat_columns=False, ensure_migrations=False)

    assert called["value"] is True


def test_init_db_uses_migrations_instead_of_create_all(monkeypatch) -> None:
    events: list[str] = []

    monkeypatch.setattr(db_init_module, "migrate_database", lambda _engine: events.append("migrate"))
    monkeypatch.setattr(Base.metadata, "create_all", lambda *args, **kwargs: events.append("create_all"))

    init_db(ensure_compat_columns=False)

    assert events == ["migrate"]


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

    init_db(ensure_migrations=False)

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


def test_application_migration_supports_fresh_sqlite(tmp_path: Path) -> None:
    database_path = tmp_path / "migrated.db"
    database_url = _sqlite_url(database_path)
    database_engine = create_database_engine(Settings(_env_file=None, database_url=database_url))
    try:
        migrate_database(database_engine)
        schema = inspect(database_engine)
        table_names = set(schema.get_table_names())
        issue_columns = {column["name"] for column in schema.get_columns("issues")}
        metric_columns = {column["name"] for column in schema.get_columns("metric_snapshots")}
        sprint_metric_columns = {column["name"] for column in schema.get_columns("sprint_metric_snapshots")}
        signal_columns = {column["name"] for column in schema.get_columns("release_signals")}
    finally:
        database_engine.dispose()

    assert {
        "alembic_version",
        "issue_history",
        "issue_sprints",
        "issues",
        "metric_snapshots",
        "operational_status",
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
        "ruleset_version",
        "confidence_score",
        "confidence_status",
        "calculation_provenance",
    }.issubset(metric_columns)
    assert {
        "jira_created_at",
        "jira_updated_at",
        "jira_blocker_flag",
        "jira_changelog_complete",
    }.issubset(issue_columns)
    assert {
        "bugs_created_during_sprint",
        "bugs_created_during_sprint_issue_keys",
        "bugs_created_during_sprint_status",
        "bugs_created_during_sprint_missing_created_at_issue_keys",
        "delivery_confidence_components",
        "delivery_confidence_inputs",
        "delivery_confidence_score",
        "delivery_confidence_status",
        "delivery_confidence_explanations",
        "story_point_total_count",
        "story_point_pointed_count",
        "story_point_unpointed_count",
        "story_point_coverage_pct",
        "story_point_unpointed_issue_keys",
        "ruleset_version",
        "calculation_provenance",
    }.issubset(sprint_metric_columns)
    assert {
        "metric_snapshot_id",
        "ruleset_version",
        "confidence_score",
        "reason_details",
        "release_gates",
        "readiness_evidence",
        "risk_aging_evidence",
        "calculated_at",
    }.issubset(signal_columns)


def test_migrate_database_upgrades_unversioned_legacy_sqlite_and_preserves_data(tmp_path: Path) -> None:
    database_path = tmp_path / "legacy.db"
    database_url = _sqlite_url(database_path)
    database_engine = create_database_engine(Settings(_env_file=None, database_url=database_url))
    alembic_config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))

    try:
        with database_engine.begin() as connection:
            alembic_config.attributes["connection"] = connection
            command.upgrade(alembic_config, "20260430_0007")
            connection.execute(
                text(
                    "INSERT INTO releases "
                    "(release_id, name, project_key, description, status, start_date, release_date) "
                    "VALUES ('legacy-release', 'Legacy release', 'LEG', NULL, 'unreleased', NULL, NULL)"
                )
            )
            connection.execute(text("DROP TABLE alembic_version"))

        migrate_database(database_engine)

        schema = inspect(database_engine)
        assert "ruleset_version" in {column["name"] for column in schema.get_columns("metric_snapshots")}
        assert "jira_created_at" in {column["name"] for column in schema.get_columns("issues")}
        with database_engine.connect() as connection:
            assert connection.scalar(text("SELECT version_num FROM alembic_version")) == "20260716_0011"
            assert connection.scalar(
                text("SELECT name FROM releases WHERE release_id = 'legacy-release'")
            ) == "Legacy release"

        backup_path = tmp_path / "legacy.db.pre-20260716_0011.bak"
        assert backup_path.is_file()
        backup_mtime = backup_path.stat().st_mtime_ns

        migrate_database(database_engine)

        assert backup_path.stat().st_mtime_ns == backup_mtime
    finally:
        database_engine.dispose()


def test_migrate_database_rejects_unknown_unversioned_schema(tmp_path: Path) -> None:
    database_path = tmp_path / "unknown.db"
    database_engine = create_database_engine(Settings(_env_file=None, database_url=_sqlite_url(database_path)))

    try:
        with database_engine.begin() as connection:
            connection.execute(text("CREATE TABLE releases (id INTEGER PRIMARY KEY)"))

        with pytest.raises(RuntimeError, match="incomplete or inconsistent"):
            migrate_database(database_engine)

        with database_engine.connect() as connection:
            assert "releases" in inspect(connection).get_table_names()
            assert "alembic_version" not in inspect(connection).get_table_names()
    finally:
        database_engine.dispose()
