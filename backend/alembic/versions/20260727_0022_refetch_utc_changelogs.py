"""Refetch Jira data after normalizing persisted timestamps to UTC.

Revision ID: 20260727_0022
Revises: 20260726_0021
Create Date: 2026-07-27 00:22:00
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260727_0022"
down_revision: str | None = "20260726_0021"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    issue_history = sa.table("issue_history")
    issues = sa.table(
        "issues",
        sa.column("jira_changelog_complete", sa.Boolean()),
    )
    op.execute(issue_history.delete())
    op.execute(
        issues.update()
        .where(issues.c.jira_changelog_complete.is_(True))
        .values(jira_changelog_complete=False)
    )


def downgrade() -> None:
    # Removed source history cannot be reconstructed safely without Jira.
    pass
