"""Persist Jira issue time and sprint bug availability evidence.

Revision ID: 20260716_0009
Revises: 20260716_0008
Create Date: 2026-07-16 00:09:00
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260716_0009"
down_revision: str | None = "20260716_0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("issues", sa.Column("jira_created_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("issues", sa.Column("jira_updated_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("issues", sa.Column("jira_blocker_flag", sa.Boolean(), nullable=True))
    op.add_column(
        "issues",
        sa.Column("jira_changelog_complete", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        "sprint_metric_snapshots",
        sa.Column(
            "bugs_created_during_sprint_status",
            sa.String(length=32),
            nullable=False,
            server_default="NOT_COMPUTED",
        ),
    )
    op.add_column(
        "sprint_metric_snapshots",
        sa.Column(
            "bugs_created_during_sprint_missing_created_at_issue_keys",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'[]'"),
        ),
    )
    if op.get_bind().dialect.name != "sqlite":
        op.alter_column("issues", "jira_changelog_complete", server_default=None)
        op.alter_column("sprint_metric_snapshots", "bugs_created_during_sprint_status", server_default=None)
        op.alter_column(
            "sprint_metric_snapshots",
            "bugs_created_during_sprint_missing_created_at_issue_keys",
            server_default=None,
        )


def downgrade() -> None:
    op.drop_column("sprint_metric_snapshots", "bugs_created_during_sprint_missing_created_at_issue_keys")
    op.drop_column("sprint_metric_snapshots", "bugs_created_during_sprint_status")
    op.drop_column("issues", "jira_changelog_complete")
    op.drop_column("issues", "jira_blocker_flag")
    op.drop_column("issues", "jira_updated_at")
    op.drop_column("issues", "jira_created_at")
