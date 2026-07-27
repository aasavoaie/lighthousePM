"""Refetch changelogs after configured Jira field IDs became authoritative.

Revision ID: 20260726_0021
Revises: 20260726_0020
Create Date: 2026-07-26 00:21:00
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260726_0021"
down_revision: str | None = "20260726_0020"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    issues = sa.table(
        "issues",
        sa.column("jira_changelog_complete", sa.Boolean()),
    )
    op.execute(
        issues.update()
        .where(issues.c.jira_changelog_complete.is_(True))
        .values(jira_changelog_complete=False)
    )


def downgrade() -> None:
    # Completeness cannot be reconstructed safely after a sync may have run.
    pass
