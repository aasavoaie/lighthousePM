from sqlalchemy import text

from app.db.base import Base
from app.db.session import engine
from app.models import Issue, IssueHistory, MetricSnapshot, OperationalStatus, Release, ReleaseSignal


def init_db(*, ensure_compat_columns: bool = True) -> None:
    """Create tables for local development when they do not exist."""
    _ = (Issue, IssueHistory, MetricSnapshot, OperationalStatus, Release, ReleaseSignal)
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
    ]
    with engine.begin() as connection:
        for statement in statements:
            connection.execute(text(statement))
