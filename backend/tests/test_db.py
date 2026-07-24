from inspect import signature
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import inspect, text
from sqlalchemy.engine import URL
from sqlalchemy.pool import StaticPool
import pytest

from app import models
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
    assert models.Release.metadata is Base.metadata
    table_names = set(Base.metadata.tables.keys())
    assert {
        "issues",
        "issue_history",
        "releases",
        "metric_snapshots",
        "release_signals",
    }.issubset(table_names)


def test_init_db_uses_only_migration_orchestrator(monkeypatch) -> None:
    events: list[str] = []

    monkeypatch.setattr(db_init_module, "migrate_database", lambda _engine: events.append("migrate"))
    monkeypatch.setattr(Base.metadata, "create_all", lambda *args, **kwargs: events.append("create_all"))

    init_db()

    assert events == ["migrate"]


def test_init_db_has_no_schema_bypass_parameters() -> None:
    assert list(signature(init_db).parameters) == []


def test_init_db_module_has_no_runtime_schema_fallback_or_ddl() -> None:
    source = Path(db_init_module.__file__).read_text(encoding="utf-8")

    assert "create_all" not in source
    assert "ALTER TABLE" not in source
    assert "CREATE INDEX" not in source


def test_migration_graph_has_single_head() -> None:
    config = Config()
    config.set_main_option(
        "script_location",
        str(Path(__file__).resolve().parents[1] / "alembic"),
    )

    assert ScriptDirectory.from_config(config).get_heads() == ["20260724_0018"]


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
        issue_column_details = {column["name"]: column for column in schema.get_columns("issues")}
        issue_columns = set(issue_column_details)
        metric_column_details = {
            column["name"]: column for column in schema.get_columns("metric_snapshots")
        }
        metric_columns = set(metric_column_details)
        sprint_metric_columns = {column["name"] for column in schema.get_columns("sprint_metric_snapshots")}
        sprint_metric_column_details = {
            column["name"]: column
            for column in schema.get_columns("sprint_metric_snapshots")
        }
        signal_columns = {column["name"] for column in schema.get_columns("release_signals")}
        with database_engine.connect() as connection:
            current_revision = connection.scalar(text("SELECT version_num FROM alembic_version"))

        migrate_database(database_engine)
        with database_engine.connect() as connection:
            revision_after_second_start = connection.scalar(
                text("SELECT version_num FROM alembic_version")
            )
    finally:
        database_engine.dispose()

    assert {
        "alembic_version",
        "issue_history",
        "issue_sprints",
        "issues",
        "jira_project_sync_state",
        "metric_snapshots",
        "operational_status",
        "release_signals",
        "releases",
        "sprint_metric_snapshots",
        "sprints",
    }.issubset(table_names)
    assert current_revision == "20260724_0018"
    assert revision_after_second_start == current_revision
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
        "jira_assignee_id",
    }.issubset(issue_columns)
    assert issue_column_details["issue_type"]["nullable"] is True
    assert issue_column_details["status"]["nullable"] is True
    assert metric_column_details["scope_churn_7d_pct"]["nullable"] is True
    assert sprint_metric_column_details["committed_scope"]["nullable"] is True
    assert sprint_metric_column_details["completed_scope_pct"]["nullable"] is True
    assert sprint_metric_column_details["in_progress_count"]["nullable"] is True
    assert sprint_metric_column_details["not_started_count"]["nullable"] is True
    assert sprint_metric_column_details["rollover_count"]["nullable"] is True
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
        "workload_concentration_pct",
        "workload_distribution_status",
        "workload_distribution_explanations",
        "workload_distribution_evidence",
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
    sync_state_columns = {
        column["name"] for column in schema.get_columns("jira_project_sync_state")
    }
    assert {
        "project_key",
        "last_successful_jira_updated_at",
        "last_successful_sync_at",
    }.issubset(sync_state_columns)


def test_nullable_issue_classification_migration_round_trip(tmp_path: Path) -> None:
    database_path = tmp_path / "nullable-source-fields.db"
    database_engine = create_database_engine(Settings(_env_file=None, database_url=_sqlite_url(database_path)))
    alembic_config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))

    try:
        with database_engine.begin() as connection:
            alembic_config.attributes["connection"] = connection
            command.upgrade(alembic_config, "20260716_0011")
            connection.execute(
                text(
                    "INSERT INTO releases (release_id, name, project_key) "
                    "VALUES ('REL-1', 'Release 1', 'LHPM')"
                )
            )
            connection.execute(
                text(
                    "INSERT INTO issues "
                    "(issue_key, summary, issue_type, status, release_id, is_blocker) "
                    "VALUES ('LHPM-1', 'Known classifications', 'Story', 'To Do', 'REL-1', 0)"
                )
            )

            command.upgrade(alembic_config, "20260717_0012")
            upgraded_columns = {
                column["name"]: column for column in inspect(connection).get_columns("issues")
            }
            assert upgraded_columns["issue_type"]["nullable"] is True
            assert upgraded_columns["status"]["nullable"] is True
            connection.execute(
                text(
                    "INSERT INTO issues "
                    "(issue_key, summary, issue_type, status, release_id, is_blocker) "
                    "VALUES ('LHPM-2', 'Missing classifications', NULL, NULL, 'REL-1', 0)"
                )
            )

            command.downgrade(alembic_config, "20260716_0011")
            downgraded_columns = {
                column["name"]: column for column in inspect(connection).get_columns("issues")
            }
            assert downgraded_columns["issue_type"]["nullable"] is False
            assert downgraded_columns["status"]["nullable"] is False
            assert connection.execute(
                text("SELECT issue_type, status FROM issues WHERE issue_key = 'LHPM-2'")
            ).one() == ("", "")
            assert connection.execute(
                text("SELECT issue_type, status FROM issues WHERE issue_key = 'LHPM-1'")
            ).one() == ("Story", "To Do")
    finally:
        database_engine.dispose()


def test_nullable_scope_churn_percentage_migration_round_trip(tmp_path: Path) -> None:
    database_path = tmp_path / "nullable-scope-churn.db"
    database_engine = create_database_engine(
        Settings(_env_file=None, database_url=_sqlite_url(database_path))
    )
    alembic_config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))

    try:
        with database_engine.begin() as connection:
            alembic_config.attributes["connection"] = connection
            command.upgrade(alembic_config, "20260717_0012")
            connection.execute(
                text(
                    "INSERT INTO releases (release_id, name, project_key) "
                    "VALUES ('REL-1', 'Release 1', 'LHPM')"
                )
            )

            command.upgrade(alembic_config, "20260717_0013")
            upgraded_columns = {
                column["name"]: column
                for column in inspect(connection).get_columns("metric_snapshots")
            }
            assert upgraded_columns["scope_churn_7d_pct"]["nullable"] is True
            connection.execute(
                text(
                    "INSERT INTO metric_snapshots "
                    "(release_id, snapshot_at, open_blockers, open_high_severity_bugs, "
                    "scope_completed_pct, scope_churn_7d_pct, reopen_rate_pct) "
                    "VALUES ('REL-1', CURRENT_TIMESTAMP, 0, 0, 0, NULL, 0)"
                )
            )

            command.downgrade(alembic_config, "20260717_0012")
            downgraded_columns = {
                column["name"]: column
                for column in inspect(connection).get_columns("metric_snapshots")
            }
            assert downgraded_columns["scope_churn_7d_pct"]["nullable"] is False
            assert connection.scalar(
                text("SELECT scope_churn_7d_pct FROM metric_snapshots")
            ) == 0.0
    finally:
        database_engine.dispose()


def test_nullable_reopen_event_rate_migration_round_trip(tmp_path: Path) -> None:
    database_path = tmp_path / "nullable-reopen-rate.db"
    database_engine = create_database_engine(
        Settings(_env_file=None, database_url=_sqlite_url(database_path))
    )
    alembic_config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))

    try:
        with database_engine.begin() as connection:
            alembic_config.attributes["connection"] = connection
            command.upgrade(alembic_config, "20260717_0013")
            connection.execute(
                text(
                    "INSERT INTO releases (release_id, name, project_key) "
                    "VALUES ('REL-1', 'Release 1', 'LHPM')"
                )
            )
            connection.execute(
                text(
                    "INSERT INTO sprints (sprint_id, name, state, project_key) "
                    "VALUES ('10', 'Sprint 10', 'active', 'LHPM')"
                )
            )

            command.upgrade(alembic_config, "20260717_0014")
            release_columns = {
                column["name"]: column
                for column in inspect(connection).get_columns("metric_snapshots")
            }
            sprint_columns = {
                column["name"]: column
                for column in inspect(connection).get_columns("sprint_metric_snapshots")
            }
            assert release_columns["reopen_rate_pct"]["nullable"] is True
            assert sprint_columns["reopen_rate_pct"]["nullable"] is True
            connection.execute(
                text(
                    "INSERT INTO metric_snapshots "
                    "(release_id, snapshot_at, open_blockers, open_high_severity_bugs, "
                    "scope_completed_pct, scope_churn_7d_pct, reopen_rate_pct) "
                    "VALUES ('REL-1', CURRENT_TIMESTAMP, 0, 0, 0, 0, NULL)"
                )
            )
            connection.execute(
                text(
                    "INSERT INTO sprint_metric_snapshots "
                    "(sprint_id, snapshot_at, committed_scope, completed_scope_pct, "
                    "open_blockers, open_high_severity_bugs, in_progress_count, "
                    "not_started_count, rollover_count, reopen_rate_pct) "
                    "VALUES ('10', CURRENT_TIMESTAMP, 0, 0, 0, 0, 0, 0, 0, NULL)"
                )
            )

            command.downgrade(alembic_config, "20260717_0013")
            release_columns = {
                column["name"]: column
                for column in inspect(connection).get_columns("metric_snapshots")
            }
            sprint_columns = {
                column["name"]: column
                for column in inspect(connection).get_columns("sprint_metric_snapshots")
            }
            assert release_columns["reopen_rate_pct"]["nullable"] is False
            assert sprint_columns["reopen_rate_pct"]["nullable"] is False
            assert connection.scalar(
                text("SELECT reopen_rate_pct FROM metric_snapshots")
            ) == 0.0
            assert connection.scalar(
                text("SELECT reopen_rate_pct FROM sprint_metric_snapshots")
            ) == 0.0
    finally:
        database_engine.dispose()


def test_nullable_sprint_scope_metrics_migration_round_trip(tmp_path: Path) -> None:
    database_path = tmp_path / "nullable-sprint-scope.db"
    database_engine = create_database_engine(
        Settings(_env_file=None, database_url=_sqlite_url(database_path))
    )
    alembic_config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))

    try:
        with database_engine.begin() as connection:
            alembic_config.attributes["connection"] = connection
            command.upgrade(alembic_config, "20260717_0014")
            connection.execute(
                text(
                    "INSERT INTO sprints (sprint_id, name, state, project_key) "
                    "VALUES ('10', 'Sprint 10', 'active', 'LHPM')"
                )
            )

            command.upgrade(alembic_config, "20260717_0015")
            upgraded_columns = {
                column["name"]: column
                for column in inspect(connection).get_columns("sprint_metric_snapshots")
            }
            assert upgraded_columns["committed_scope"]["nullable"] is True
            assert upgraded_columns["completed_scope_pct"]["nullable"] is True
            connection.execute(
                text(
                    "INSERT INTO sprint_metric_snapshots "
                    "(sprint_id, snapshot_at, committed_scope, completed_scope_pct, "
                    "open_blockers, open_high_severity_bugs, in_progress_count, "
                    "not_started_count, rollover_count) "
                    "VALUES ('10', CURRENT_TIMESTAMP, NULL, NULL, 0, 0, 0, 0, 0)"
                )
            )

            command.downgrade(alembic_config, "20260717_0014")
            downgraded_columns = {
                column["name"]: column
                for column in inspect(connection).get_columns("sprint_metric_snapshots")
            }
            assert downgraded_columns["committed_scope"]["nullable"] is False
            assert downgraded_columns["completed_scope_pct"]["nullable"] is False
            assert connection.execute(
                text(
                    "SELECT committed_scope, completed_scope_pct "
                    "FROM sprint_metric_snapshots"
                )
            ).one() == (0, 0.0)
    finally:
        database_engine.dispose()


def test_nullable_sprint_work_state_metrics_migration_round_trip(tmp_path: Path) -> None:
    database_path = tmp_path / "nullable-sprint-work-state.db"
    database_engine = create_database_engine(
        Settings(_env_file=None, database_url=_sqlite_url(database_path))
    )
    alembic_config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))

    try:
        with database_engine.begin() as connection:
            alembic_config.attributes["connection"] = connection
            command.upgrade(alembic_config, "20260717_0015")
            connection.execute(
                text(
                    "INSERT INTO sprints (sprint_id, name, state, project_key) "
                    "VALUES ('10', 'Sprint 10', 'active', 'LHPM')"
                )
            )

            command.upgrade(alembic_config, "20260717_0016")
            upgraded_columns = {
                column["name"]: column
                for column in inspect(connection).get_columns("sprint_metric_snapshots")
            }
            for column_name in (
                "in_progress_count",
                "not_started_count",
                "rollover_count",
            ):
                assert upgraded_columns[column_name]["nullable"] is True
            connection.execute(
                text(
                    "INSERT INTO sprint_metric_snapshots "
                    "(sprint_id, snapshot_at, committed_scope, completed_scope_pct, "
                    "open_blockers, open_high_severity_bugs, in_progress_count, "
                    "not_started_count, rollover_count) "
                    "VALUES ('10', CURRENT_TIMESTAMP, NULL, NULL, 0, 0, NULL, NULL, NULL)"
                )
            )

            command.downgrade(alembic_config, "20260717_0015")
            downgraded_columns = {
                column["name"]: column
                for column in inspect(connection).get_columns("sprint_metric_snapshots")
            }
            for column_name in (
                "in_progress_count",
                "not_started_count",
                "rollover_count",
            ):
                assert downgraded_columns[column_name]["nullable"] is False
            assert connection.execute(
                text(
                    "SELECT in_progress_count, not_started_count, rollover_count "
                    "FROM sprint_metric_snapshots"
                )
            ).one() == (0, 0, 0)
    finally:
        database_engine.dispose()


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
            assert connection.scalar(text("SELECT version_num FROM alembic_version")) == "20260724_0018"
            assert connection.scalar(
                text("SELECT name FROM releases WHERE release_id = 'legacy-release'")
            ) == "Legacy release"

        backup_path = tmp_path / "legacy.db.pre-20260724_0018.bak"
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
