"""Deterministic identification of supported LighthousePM schema revisions."""

from dataclasses import dataclass, field
from typing import Literal

from alembic.migration import MigrationContext
from sqlalchemy import inspect
from sqlalchemy.engine import Connection


@dataclass(frozen=True)
class LegacyRevisionShape:
    revision: str
    tables: frozenset[str] = field(default_factory=frozenset)
    columns: dict[str, frozenset[str]] = field(default_factory=dict)


@dataclass(frozen=True)
class SchemaRevisionIdentity:
    revision: str
    kind: Literal["alembic", "recognized_legacy"]


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

# These application-owned markers were introduced only after the supported
# pre-Alembic adoption range. Their presence must not be mislabeled as the last
# supported legacy revision.
POST_LEGACY_REVISION_MARKERS = (
    LegacyRevisionShape(
        revision="20260716_0011",
        tables=frozenset({"operational_status"}),
    ),
    LegacyRevisionShape(
        revision="20260720_0017",
        columns={
            "sprint_metric_snapshots": frozenset(
                {
                    "workload_concentration_pct",
                    "workload_distribution_status",
                    "workload_distribution_explanations",
                    "workload_distribution_evidence",
                }
            )
        },
    ),
    LegacyRevisionShape(
        revision="20260724_0018",
        tables=frozenset({"jira_project_sync_state"}),
    ),
)


def infer_legacy_revision(connection: Connection) -> str:
    schema = inspect(connection)
    table_names = set(schema.get_table_names())
    columns_by_table = {
        table_name: {column["name"] for column in schema.get_columns(table_name)}
        for table_name in table_names
    }
    inferred_revision: str | None = None

    if any(
        _shape_is_partially_present(marker, table_names, columns_by_table)
        for marker in POST_LEGACY_REVISION_MARKERS
    ):
        raise RuntimeError(
            "Existing unversioned database contains application schema newer than the supported "
            "legacy registry; automatic migration was stopped"
        )

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


def identify_schema_revision(
    connection: Connection,
    known_revisions: set[str],
) -> SchemaRevisionIdentity:
    schema = inspect(connection)
    table_names = set(schema.get_table_names())
    has_application_schema = bool(table_names - {"alembic_version"})
    current_revisions = MigrationContext.configure(connection).get_current_heads()

    if len(current_revisions) > 1:
        raise RuntimeError("Database records multiple Alembic revisions")

    current_revision = current_revisions[0] if current_revisions else None
    if "alembic_version" in table_names and current_revision is None:
        raise RuntimeError("Alembic version table exists without a recorded revision")

    if current_revision is not None:
        if current_revision not in known_revisions:
            raise RuntimeError(f"Database records unknown Alembic revision {current_revision!r}")
        return SchemaRevisionIdentity(revision=current_revision, kind="alembic")

    if not has_application_schema:
        raise RuntimeError("Database does not contain a LighthousePM application schema")

    return SchemaRevisionIdentity(
        revision=infer_legacy_revision(connection),
        kind="recognized_legacy",
    )


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
