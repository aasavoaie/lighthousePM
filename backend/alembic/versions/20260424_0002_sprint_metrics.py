"""Add sprint metadata and sprint metric snapshots.

Revision ID: 20260424_0002
Revises: 20260407_0001
Create Date: 2026-04-24 00:02:00
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260424_0002"
down_revision: str | None = "20260407_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "sprints",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("sprint_id", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("state", sa.String(length=32), nullable=False),
        sa.Column("project_key", sa.String(length=64), nullable=False),
        sa.Column("board_id", sa.String(length=64), nullable=True),
        sa.Column("start_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("end_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("complete_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("goal", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_sprints"),
    )
    op.create_index("ix_sprints_sprint_id", "sprints", ["sprint_id"], unique=True)
    op.create_index("ix_sprints_name", "sprints", ["name"], unique=False)
    op.create_index("ix_sprints_state", "sprints", ["state"], unique=False)
    op.create_index("ix_sprints_project_key", "sprints", ["project_key"], unique=False)

    op.create_table(
        "issue_sprints",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("issue_key", sa.String(length=32), nullable=False),
        sa.Column("sprint_id", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["issue_key"], ["issues.issue_key"], name="fk_issue_sprints_issue_key_issues", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["sprint_id"], ["sprints.sprint_id"], name="fk_issue_sprints_sprint_id_sprints", ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name="pk_issue_sprints"),
        sa.UniqueConstraint("issue_key", "sprint_id", name="uq_issue_sprints_issue_key_sprint_id"),
    )
    op.create_index("ix_issue_sprints_issue_key", "issue_sprints", ["issue_key"], unique=False)
    op.create_index("ix_issue_sprints_sprint_id", "issue_sprints", ["sprint_id"], unique=False)

    op.create_table(
        "sprint_metric_snapshots",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("sprint_id", sa.String(length=64), nullable=False),
        sa.Column("snapshot_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("committed_scope", sa.Integer(), nullable=False),
        sa.Column("completed_scope_pct", sa.Float(), nullable=False),
        sa.Column("open_blockers", sa.Integer(), nullable=False),
        sa.Column("open_high_severity_bugs", sa.Integer(), nullable=False),
        sa.Column("in_progress_count", sa.Integer(), nullable=False),
        sa.Column("not_started_count", sa.Integer(), nullable=False),
        sa.Column("rollover_count", sa.Integer(), nullable=False),
        sa.Column("median_cycle_time_days", sa.Float(), nullable=True),
        sa.Column("reopen_rate_pct", sa.Float(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["sprint_id"], ["sprints.sprint_id"], name="fk_sprint_metric_snapshots_sprint_id_sprints", ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name="pk_sprint_metric_snapshots"),
    )
    op.create_index("ix_sprint_metric_snapshots_sprint_id", "sprint_metric_snapshots", ["sprint_id"], unique=False)
    op.create_index("ix_sprint_metric_snapshots_snapshot_at", "sprint_metric_snapshots", ["snapshot_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_sprint_metric_snapshots_snapshot_at", table_name="sprint_metric_snapshots")
    op.drop_index("ix_sprint_metric_snapshots_sprint_id", table_name="sprint_metric_snapshots")
    op.drop_table("sprint_metric_snapshots")

    op.drop_index("ix_issue_sprints_sprint_id", table_name="issue_sprints")
    op.drop_index("ix_issue_sprints_issue_key", table_name="issue_sprints")
    op.drop_table("issue_sprints")

    op.drop_index("ix_sprints_project_key", table_name="sprints")
    op.drop_index("ix_sprints_state", table_name="sprints")
    op.drop_index("ix_sprints_name", table_name="sprints")
    op.drop_index("ix_sprints_sprint_id", table_name="sprints")
    op.drop_table("sprints")
