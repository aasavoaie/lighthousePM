"""Persist Jira sync visibility state.

Revision ID: 20260724_0019
Revises: 20260724_0018
Create Date: 2026-07-24 00:19:00
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260724_0019"
down_revision: str | None = "20260724_0018"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("jira_project_sync_state") as batch_op:
        batch_op.add_column(
            sa.Column(
                "current_sync_status",
                sa.String(length=32),
                nullable=False,
                server_default="idle",
            )
        )
        batch_op.add_column(sa.Column("last_failed_sync_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column("last_failure_summary", sa.String(length=500), nullable=True))
        batch_op.add_column(sa.Column("latest_sync_result", sa.JSON(), nullable=True))

    with op.batch_alter_table("jira_project_sync_state") as batch_op:
        batch_op.alter_column("current_sync_status", server_default=None)


def downgrade() -> None:
    with op.batch_alter_table("jira_project_sync_state") as batch_op:
        batch_op.drop_column("latest_sync_result")
        batch_op.drop_column("last_failure_summary")
        batch_op.drop_column("last_failed_sync_at")
        batch_op.drop_column("current_sync_status")
