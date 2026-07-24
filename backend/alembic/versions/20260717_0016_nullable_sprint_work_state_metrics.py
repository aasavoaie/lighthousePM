"""Allow unavailable sprint work-state metrics.

Revision ID: 20260717_0016
Revises: 20260717_0015
Create Date: 2026-07-17 00:16:00
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260717_0016"
down_revision: str | None = "20260717_0015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("sprint_metric_snapshots") as batch_op:
        for column_name in (
            "in_progress_count",
            "not_started_count",
            "rollover_count",
        ):
            batch_op.alter_column(
                column_name,
                existing_type=sa.Integer(),
                nullable=True,
            )


def downgrade() -> None:
    # Zero was the legacy representation for unavailable sprint work-state metrics.
    for column_name in (
        "in_progress_count",
        "not_started_count",
        "rollover_count",
    ):
        op.execute(
            sa.text(
                f"UPDATE sprint_metric_snapshots SET {column_name} = 0 "
                f"WHERE {column_name} IS NULL"
            )
        )
    with op.batch_alter_table("sprint_metric_snapshots") as batch_op:
        for column_name in (
            "in_progress_count",
            "not_started_count",
            "rollover_count",
        ):
            batch_op.alter_column(
                column_name,
                existing_type=sa.Integer(),
                nullable=False,
            )
