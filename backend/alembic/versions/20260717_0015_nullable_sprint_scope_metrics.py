"""Allow unavailable current-sprint-scope metrics.

Revision ID: 20260717_0015
Revises: 20260717_0014
Create Date: 2026-07-17 00:15:00
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260717_0015"
down_revision: str | None = "20260717_0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("sprint_metric_snapshots") as batch_op:
        batch_op.alter_column(
            "committed_scope",
            existing_type=sa.Integer(),
            nullable=True,
        )
        batch_op.alter_column(
            "completed_scope_pct",
            existing_type=sa.Float(),
            nullable=True,
        )


def downgrade() -> None:
    # Zero was the legacy representation for unavailable sprint scope metrics.
    op.execute(
        sa.text(
            "UPDATE sprint_metric_snapshots SET committed_scope = 0 "
            "WHERE committed_scope IS NULL"
        )
    )
    op.execute(
        sa.text(
            "UPDATE sprint_metric_snapshots SET completed_scope_pct = 0 "
            "WHERE completed_scope_pct IS NULL"
        )
    )
    with op.batch_alter_table("sprint_metric_snapshots") as batch_op:
        batch_op.alter_column(
            "committed_scope",
            existing_type=sa.Integer(),
            nullable=False,
        )
        batch_op.alter_column(
            "completed_scope_pct",
            existing_type=sa.Float(),
            nullable=False,
        )
