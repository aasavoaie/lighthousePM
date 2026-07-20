"""Allow missing Jira issue classification source values.

Revision ID: 20260717_0012
Revises: 20260716_0011
Create Date: 2026-07-17 00:12:00
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260717_0012"
down_revision: str | None = "20260716_0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("issues") as batch_op:
        batch_op.alter_column(
            "issue_type",
            existing_type=sa.String(length=64),
            nullable=True,
        )
        batch_op.alter_column(
            "status",
            existing_type=sa.String(length=64),
            nullable=True,
        )


def downgrade() -> None:
    # Empty strings were the legacy representation for missing Jira values.
    # Restore that representation before reinstating the old NOT NULL contract.
    op.execute(sa.text("UPDATE issues SET issue_type = '' WHERE issue_type IS NULL"))
    op.execute(sa.text("UPDATE issues SET status = '' WHERE status IS NULL"))
    with op.batch_alter_table("issues") as batch_op:
        batch_op.alter_column(
            "issue_type",
            existing_type=sa.String(length=64),
            nullable=False,
        )
        batch_op.alter_column(
            "status",
            existing_type=sa.String(length=64),
            nullable=False,
        )
