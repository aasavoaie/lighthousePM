"""Allow unavailable release scope-churn percentages.

Revision ID: 20260717_0013
Revises: 20260717_0012
Create Date: 2026-07-17 00:13:00
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260717_0013"
down_revision: str | None = "20260717_0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("metric_snapshots") as batch_op:
        batch_op.alter_column(
            "scope_churn_7d_pct",
            existing_type=sa.Float(),
            nullable=True,
        )


def downgrade() -> None:
    # Zero was the legacy representation for an unavailable churn percentage.
    op.execute(
        sa.text(
            "UPDATE metric_snapshots SET scope_churn_7d_pct = 0 "
            "WHERE scope_churn_7d_pct IS NULL"
        )
    )
    with op.batch_alter_table("metric_snapshots") as batch_op:
        batch_op.alter_column(
            "scope_churn_7d_pct",
            existing_type=sa.Float(),
            nullable=False,
        )
