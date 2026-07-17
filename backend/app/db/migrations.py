"""Deterministic database migration orchestration for application startup."""

from dataclasses import dataclass, field
from pathlib import Path
import sqlite3

from alembic import command
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import inspect
from sqlalchemy.engine import Connection, Engine


@dataclass(frozen=True)
class LegacyRevisionShape:
    revision: str
    tables: frozenset[str] = field(default_factory=frozenset)
    columns: dict[str, frozenset[str]] = field(default_factory=dict)


LEGACY_REVISION_SHAPES = (
    LegacyRevisionShape(
        revision="20260407_0001",
        tables=frozenset({"releases", "issues", "issue_history", "metric_snapshots", "release_signals"}),
    ),
    LegacyRevisionShape(
        revision="20260424_0002",
        tables=frozenset({"sprints", "issue_sprints", "sprint_metric_snapshots"}),
    ),
    LegacyRevisionShape(
        revision="20260425_0003",
        columns={
            "metric_snapshots": frozenset({"open_blocker_issue_keys", "open_high_severity_bug_issue_keys"}),
            "sprint_metric_snapshots": frozenset(
                {"open_blocker_issue_keys", "open_high_severity_bug_issue_keys"}
            ),
        },
    ),
    LegacyRevisionShape(
        revision="20260427_0004",
        columns={
            "issues": frozenset({"story_points"}),
            "sprint_metric_snapshots": frozenset(
                {"delivery_confidence_score", "delivery_confidence_components", "delivery_confidence_inputs"}
            ),
        },
    ),
    LegacyRevisionShape(
        revision="20260428_0005",
        columns={
            "sprint_metric_snapshots": frozenset(
                {"bugs_created_during_sprint", "bugs_created_during_sprint_issue_keys"}
            )
        },
    ),
    LegacyRevisionShape(
        revision="20260429_0006",
        columns={"metric_snapshots": frozenset({"completed_tickets"})},
    ),
    LegacyRevisionShape(
        revision="20260430_0007",
        columns={"metric_snapshots": frozenset({"scope_added_7d_count", "scope_removed_7d_count"})},
    ),
    LegacyRevisionShape(
        revision="20260716_0008",
        columns={
            "sprint_metric_snapshots": frozenset(
                {
                    "story_point_total_count",
                    "story_point_pointed_count",
                    "story_point_unpointed_count",
                    "story_point_coverage_pct",
                    "story_point_unpointed_issue_keys",
                    "delivery_confidence_status",
                    "delivery_confidence_explanations",
                }
            )
        },
    ),
    LegacyRevisionShape(
        revision="20260716_0009",
        columns={
            "issues": frozenset(
                {"jira_created_at", "jira_updated_at", "jira_blocker_flag", "jira_changelog_complete"}
            ),
            "sprint_metric_snapshots": frozenset(
                {"bugs_created_during_sprint_status", "bugs_created_during_sprint_missing_created_at_issue_keys"}
            ),
        },
    ),
    LegacyRevisionShape(
        revision="20260716_0010",
        columns={
            "metric_snapshots": frozenset(
                {"ruleset_version", "confidence_score", "confidence_status", "calculation_provenance"}
            ),
            "sprint_metric_snapshots": frozenset({"ruleset_version", "calculation_provenance"}),
            "release_signals": frozenset(
                {
                    "metric_snapshot_id",
                    "ruleset_version",
                    "confidence_score",
                    "reason_details",
                    "release_gates",
                    "readiness_evidence",
                    "risk_aging_evidence",
                    "calculated_at",
                }
            ),
        },
    ),
)


def migrate_database(database_engine: Engine) -> None:
    """Upgrade a fresh, versioned, or recognized legacy database to Alembic head."""
    alembic_config = _build_alembic_config()
    script = ScriptDirectory.from_config(alembic_config)
    heads = script.get_heads()
    if len(heads) != 1:
        raise RuntimeError(f"Expected one Alembic head, found {len(heads)}")
    target_revision = heads[0]

    with database_engine.begin() as connection:
        current_revision = MigrationContext.configure(connection).get_current_revision()
        table_names = set(inspect(connection).get_table_names())
        has_application_schema = bool(table_names - {"alembic_version"})

        if current_revision == target_revision:
            return

        if has_application_schema and database_engine.dialect.name == "sqlite":
            _create_sqlite_backup(database_engine, target_revision)

        alembic_config.attributes["connection"] = connection
        if current_revision is None and has_application_schema:
            legacy_revision = _infer_legacy_revision(connection)
            command.stamp(alembic_config, legacy_revision)

        command.upgrade(alembic_config, "head")


def _build_alembic_config() -> Config:
    backend_directory = Path(__file__).resolve().parents[2]
    script_location = backend_directory / "alembic"
    if not script_location.is_dir():
        raise RuntimeError(f"Alembic migration scripts are unavailable at {script_location}")

    config = Config()
    config.set_main_option("script_location", str(script_location))
    return config


def _infer_legacy_revision(connection: Connection) -> str:
    schema = inspect(connection)
    table_names = set(schema.get_table_names())
    columns_by_table = {
        table_name: {column["name"] for column in schema.get_columns(table_name)}
        for table_name in table_names
    }
    inferred_revision: str | None = None

    for index, shape in enumerate(LEGACY_REVISION_SHAPES):
        if _shape_is_complete(shape, table_names, columns_by_table):
            inferred_revision = shape.revision
            continue

        later_shapes = LEGACY_REVISION_SHAPES[index:]
        if any(_shape_is_partially_present(candidate, table_names, columns_by_table) for candidate in later_shapes):
            raise RuntimeError(
                "Existing unversioned database schema is incomplete or inconsistent; "
                "automatic revision detection was stopped"
            )
        break

    if inferred_revision is None:
        raise RuntimeError(
            "Existing unversioned database schema is not a recognized LighthousePM revision; "
            "automatic migration was stopped"
        )
    return inferred_revision


def _shape_is_complete(
    shape: LegacyRevisionShape,
    table_names: set[str],
    columns_by_table: dict[str, set[str]],
) -> bool:
    if not shape.tables.issubset(table_names):
        return False
    return all(required.issubset(columns_by_table.get(table_name, set())) for table_name, required in shape.columns.items())


def _shape_is_partially_present(
    shape: LegacyRevisionShape,
    table_names: set[str],
    columns_by_table: dict[str, set[str]],
) -> bool:
    if shape.tables.intersection(table_names):
        return True
    return any(required.intersection(columns_by_table.get(table_name, set())) for table_name, required in shape.columns.items())


def _create_sqlite_backup(database_engine: Engine, target_revision: str) -> Path | None:
    database_name = database_engine.url.database
    if not database_name or database_name == ":memory:" or database_name.startswith("file:"):
        return None

    database_path = Path(database_name).expanduser().resolve()
    backup_path = database_path.with_name(f"{database_path.name}.pre-{target_revision}.bak")
    if backup_path.exists():
        return backup_path

    raw_connection = database_engine.raw_connection()
    target_connection = sqlite3.connect(backup_path)
    try:
        source_connection = raw_connection.driver_connection
        if not isinstance(source_connection, sqlite3.Connection):
            raise RuntimeError("SQLite backup requires a sqlite3 driver connection")
        source_connection.backup(target_connection)
    finally:
        target_connection.close()
        raw_connection.close()
    return backup_path
