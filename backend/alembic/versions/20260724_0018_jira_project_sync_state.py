"""Persist Jira project sync cursors.

Revision ID: 20260724_0018
Revises: 20260720_0017
Create Date: 2026-07-24 00:18:00
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260724_0018"
down_revision: str | None = "20260720_0017"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "jira_project_sync_state",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("project_key", sa.String(length=64), nullable=False),
        sa.Column("last_successful_jira_updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_successful_sync_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_jira_project_sync_state"),
        sa.UniqueConstraint("project_key", name="uq_jira_project_sync_state_project_key"),
    )
    op.create_index(
        "ix_jira_project_sync_state_project_key",
        "jira_project_sync_state",
        ["project_key"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_jira_project_sync_state_project_key",
        table_name="jira_project_sync_state",
    )
    op.drop_table("jira_project_sync_state")
