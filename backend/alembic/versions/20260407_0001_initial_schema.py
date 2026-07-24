"""Initial schema for Jira Release Signals MVP.

Revision ID: 20260407_0001
Revises:
Create Date: 2026-04-07 00:01:00
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "20260407_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "releases",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("release_id", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("project_key", sa.String(length=64), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=64), nullable=True),
        sa.Column("start_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("release_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_releases"),
    )
    op.create_index("ix_releases_release_id", "releases", ["release_id"], unique=True)
    op.create_index("ix_releases_name", "releases", ["name"], unique=False)
    op.create_index("ix_releases_project_key", "releases", ["project_key"], unique=False)

    op.create_table(
        "issues",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("issue_key", sa.String(length=32), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("issue_type", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=64), nullable=False),
        sa.Column("priority", sa.String(length=64), nullable=True),
        sa.Column("assignee", sa.String(length=128), nullable=True),
        sa.Column("release_id", sa.String(length=64), nullable=True),
        sa.Column("is_blocker", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["release_id"], ["releases.release_id"], name="fk_issues_release_id_releases", ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id", name="pk_issues"),
    )
    op.create_index("ix_issues_issue_key", "issues", ["issue_key"], unique=True)
    op.create_index("ix_issues_release_id", "issues", ["release_id"], unique=False)
    op.create_index("ix_issues_status", "issues", ["status"], unique=False)

    op.create_table(
        "issue_history",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("issue_key", sa.String(length=32), nullable=False),
        sa.Column("field_name", sa.String(length=64), nullable=False),
        sa.Column("old_value", sa.Text(), nullable=True),
        sa.Column("new_value", sa.Text(), nullable=True),
        sa.Column("changed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["issue_key"], ["issues.issue_key"], name="fk_issue_history_issue_key_issues", ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name="pk_issue_history"),
    )
    op.create_index("ix_issue_history_issue_key", "issue_history", ["issue_key"], unique=False)

    op.create_table(
        "metric_snapshots",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("release_id", sa.String(length=64), nullable=False),
        sa.Column("snapshot_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("open_blockers", sa.Integer(), nullable=False),
        sa.Column("open_high_severity_bugs", sa.Integer(), nullable=False),
        sa.Column("scope_completed_pct", sa.Float(), nullable=False),
        sa.Column("scope_churn_7d_pct", sa.Float(), nullable=False),
        sa.Column("median_cycle_time_days", sa.Float(), nullable=True),
        sa.Column("reopen_rate_pct", sa.Float(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["release_id"], ["releases.release_id"], name="fk_metric_snapshots_release_id_releases", ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name="pk_metric_snapshots"),
    )
    op.create_index("ix_metric_snapshots_release_id", "metric_snapshots", ["release_id"], unique=False)
    op.create_index("ix_metric_snapshots_snapshot_at", "metric_snapshots", ["snapshot_at"], unique=False)

    op.create_table(
        "release_signals",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("release_id", sa.String(length=64), nullable=False),
        sa.Column("signal", sa.String(length=16), nullable=False),
        sa.Column("reasons", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["release_id"], ["releases.release_id"], name="fk_release_signals_release_id_releases", ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name="pk_release_signals"),
    )
    op.create_index("ix_release_signals_release_id", "release_signals", ["release_id"], unique=False)
    op.create_index("ix_release_signals_signal", "release_signals", ["signal"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_release_signals_signal", table_name="release_signals")
    op.drop_index("ix_release_signals_release_id", table_name="release_signals")
    op.drop_table("release_signals")

    op.drop_index("ix_metric_snapshots_snapshot_at", table_name="metric_snapshots")
    op.drop_index("ix_metric_snapshots_release_id", table_name="metric_snapshots")
    op.drop_table("metric_snapshots")

    op.drop_index("ix_issue_history_issue_key", table_name="issue_history")
    op.drop_table("issue_history")

    op.drop_index("ix_issues_status", table_name="issues")
    op.drop_index("ix_issues_release_id", table_name="issues")
    op.drop_index("ix_issues_issue_key", table_name="issues")
    op.drop_table("issues")

    op.drop_index("ix_releases_project_key", table_name="releases")
    op.drop_index("ix_releases_name", table_name="releases")
    op.drop_index("ix_releases_release_id", table_name="releases")
    op.drop_table("releases")
