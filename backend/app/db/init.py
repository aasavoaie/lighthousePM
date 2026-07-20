from sqlalchemy import text

from app.db.base import Base
from app.db.session import engine
from app.db.migrations import migrate_database
from app.models import Issue, IssueHistory, MetricSnapshot, OperationalStatus, Release, ReleaseSignal


def init_db(*, ensure_compat_columns: bool = True, ensure_migrations: bool = True) -> None:
    """Migrate the configured database before application use."""
    _ = (Issue, IssueHistory, MetricSnapshot, OperationalStatus, Release, ReleaseSignal)
    if ensure_migrations:
        migrate_database(engine)
    else:
        Base.metadata.create_all(bind=engine)
    if ensure_compat_columns:
        _ensure_metric_issue_key_columns()


def _ensure_metric_issue_key_columns() -> None:
    """Keep local create_all databases compatible with metric issue-key snapshots."""
    if engine.dialect.name != "postgresql":
        return
    statements = [
        "ALTER TABLE metric_snapshots ADD COLUMN IF NOT EXISTS open_blocker_issue_keys JSON NOT NULL DEFAULT '[]'",
        (
            "ALTER TABLE metric_snapshots ADD COLUMN IF NOT EXISTS "
            "open_high_severity_bug_issue_keys JSON NOT NULL DEFAULT '[]'"
        ),
        "ALTER TABLE sprint_metric_snapshots ADD COLUMN IF NOT EXISTS open_blocker_issue_keys JSON NOT NULL DEFAULT '[]'",
        (
            "ALTER TABLE sprint_metric_snapshots ADD COLUMN IF NOT EXISTS "
            "open_high_severity_bug_issue_keys JSON NOT NULL DEFAULT '[]'"
        ),
        (
            "ALTER TABLE sprint_metric_snapshots ADD COLUMN IF NOT EXISTS "
            "bugs_created_during_sprint INTEGER NOT NULL DEFAULT 0"
        ),
        (
            "ALTER TABLE sprint_metric_snapshots ADD COLUMN IF NOT EXISTS "
            "bugs_created_during_sprint_issue_keys JSON NOT NULL DEFAULT '[]'"
        ),
        "ALTER TABLE metric_snapshots ADD COLUMN IF NOT EXISTS completed_tickets INTEGER",
        (
            "ALTER TABLE metric_snapshots ADD COLUMN IF NOT EXISTS "
            "scope_added_7d_count INTEGER NOT NULL DEFAULT 0"
        ),
        (
            "ALTER TABLE metric_snapshots ADD COLUMN IF NOT EXISTS "
            "scope_removed_7d_count INTEGER NOT NULL DEFAULT 0"
        ),
        (
            "ALTER TABLE sprint_metric_snapshots ADD COLUMN IF NOT EXISTS "
            "story_point_total_count INTEGER NOT NULL DEFAULT 0"
        ),
        (
            "ALTER TABLE sprint_metric_snapshots ADD COLUMN IF NOT EXISTS "
            "story_point_pointed_count INTEGER NOT NULL DEFAULT 0"
        ),
        (
            "ALTER TABLE sprint_metric_snapshots ADD COLUMN IF NOT EXISTS "
            "story_point_unpointed_count INTEGER NOT NULL DEFAULT 0"
        ),
        (
            "ALTER TABLE sprint_metric_snapshots ADD COLUMN IF NOT EXISTS "
            "story_point_coverage_pct DOUBLE PRECISION NOT NULL DEFAULT 0"
        ),
        (
            "ALTER TABLE sprint_metric_snapshots ADD COLUMN IF NOT EXISTS "
            "story_point_unpointed_issue_keys JSON NOT NULL DEFAULT '[]'"
        ),
        (
            "ALTER TABLE sprint_metric_snapshots ADD COLUMN IF NOT EXISTS "
            "delivery_confidence_status VARCHAR(32) NOT NULL DEFAULT 'NOT_COMPUTED'"
        ),
        (
            "ALTER TABLE sprint_metric_snapshots ADD COLUMN IF NOT EXISTS "
            "delivery_confidence_explanations JSON NOT NULL DEFAULT '[]'"
        ),
        (
            "ALTER TABLE sprint_metric_snapshots ADD COLUMN IF NOT EXISTS "
            "workload_concentration_pct DOUBLE PRECISION"
        ),
        (
            "ALTER TABLE sprint_metric_snapshots ADD COLUMN IF NOT EXISTS "
            "workload_distribution_status VARCHAR(32)"
        ),
        (
            "ALTER TABLE sprint_metric_snapshots ADD COLUMN IF NOT EXISTS "
            "workload_distribution_explanations JSON"
        ),
        (
            "ALTER TABLE sprint_metric_snapshots ADD COLUMN IF NOT EXISTS "
            "workload_distribution_evidence JSON"
        ),
        "ALTER TABLE issues ADD COLUMN IF NOT EXISTS jira_created_at TIMESTAMPTZ",
        "ALTER TABLE issues ADD COLUMN IF NOT EXISTS jira_updated_at TIMESTAMPTZ",
        "ALTER TABLE issues ADD COLUMN IF NOT EXISTS jira_assignee_id VARCHAR(128)",
        "ALTER TABLE issues ADD COLUMN IF NOT EXISTS jira_blocker_flag BOOLEAN",
        (
            "ALTER TABLE issues ADD COLUMN IF NOT EXISTS "
            "jira_changelog_complete BOOLEAN NOT NULL DEFAULT FALSE"
        ),
        (
            "ALTER TABLE sprint_metric_snapshots ADD COLUMN IF NOT EXISTS "
            "bugs_created_during_sprint_status VARCHAR(32) NOT NULL DEFAULT 'NOT_COMPUTED'"
        ),
        (
            "ALTER TABLE sprint_metric_snapshots ADD COLUMN IF NOT EXISTS "
            "bugs_created_during_sprint_missing_created_at_issue_keys JSON NOT NULL DEFAULT '[]'"
        ),
        "ALTER TABLE metric_snapshots ADD COLUMN IF NOT EXISTS ruleset_version INTEGER NOT NULL DEFAULT 0",
        "ALTER TABLE metric_snapshots ADD COLUMN IF NOT EXISTS confidence_score DOUBLE PRECISION",
        "ALTER TABLE metric_snapshots ADD COLUMN IF NOT EXISTS confidence_status VARCHAR(32)",
        "ALTER TABLE metric_snapshots ADD COLUMN IF NOT EXISTS calculation_provenance JSON NOT NULL DEFAULT '{}'",
        "ALTER TABLE sprint_metric_snapshots ADD COLUMN IF NOT EXISTS ruleset_version INTEGER NOT NULL DEFAULT 0",
        "ALTER TABLE sprint_metric_snapshots ADD COLUMN IF NOT EXISTS calculation_provenance JSON NOT NULL DEFAULT '{}'",
        "ALTER TABLE release_signals ADD COLUMN IF NOT EXISTS metric_snapshot_id INTEGER",
        "ALTER TABLE release_signals ADD COLUMN IF NOT EXISTS ruleset_version INTEGER NOT NULL DEFAULT 0",
        "ALTER TABLE release_signals ADD COLUMN IF NOT EXISTS confidence_score DOUBLE PRECISION",
        "ALTER TABLE release_signals ADD COLUMN IF NOT EXISTS reason_details JSON NOT NULL DEFAULT '[]'",
        "ALTER TABLE release_signals ADD COLUMN IF NOT EXISTS release_gates JSON NOT NULL DEFAULT '[]'",
        "ALTER TABLE release_signals ADD COLUMN IF NOT EXISTS readiness_evidence JSON NOT NULL DEFAULT '{}'",
        "ALTER TABLE release_signals ADD COLUMN IF NOT EXISTS risk_aging_evidence JSON NOT NULL DEFAULT '{}'",
        "ALTER TABLE release_signals ADD COLUMN IF NOT EXISTS calculated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()",
        (
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_release_signal_snapshot_ruleset "
            "ON release_signals (release_id, metric_snapshot_id, ruleset_version)"
        ),
    ]
    with engine.begin() as connection:
        for statement in statements:
            connection.execute(text(statement))
