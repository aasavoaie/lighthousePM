"""Allow unavailable release and sprint reopen-event rates.

Revision ID: 20260717_0014
Revises: 20260717_0013
Create Date: 2026-07-17 00:14:00
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260717_0014"
down_revision: str | None = "20260717_0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("metric_snapshots") as batch_op:
        batch_op.alter_column(
            "reopen_rate_pct",
            existing_type=sa.Float(),
            nullable=True,
        )
    with op.batch_alter_table("sprint_metric_snapshots") as batch_op:
        batch_op.alter_column(
            "reopen_rate_pct",
            existing_type=sa.Float(),
            nullable=True,
        )


def downgrade() -> None:
    # Zero was the legacy representation for an unavailable reopen rate.
    op.execute(
        sa.text(
            "UPDATE metric_snapshots SET reopen_rate_pct = 0 "
            "WHERE reopen_rate_pct IS NULL"
        )
    )
    op.execute(
        sa.text(
            "UPDATE sprint_metric_snapshots SET reopen_rate_pct = 0 "
            "WHERE reopen_rate_pct IS NULL"
        )
    )
    with op.batch_alter_table("metric_snapshots") as batch_op:
        batch_op.alter_column(
            "reopen_rate_pct",
            existing_type=sa.Float(),
            nullable=False,
        )
    with op.batch_alter_table("sprint_metric_snapshots") as batch_op:
        batch_op.alter_column(
            "reopen_rate_pct",
            existing_type=sa.Float(),
            nullable=False,
        )
