"""Persist authoritative sprint workload distribution.

Revision ID: 20260720_0017
Revises: 20260717_0016
Create Date: 2026-07-20 00:17:00
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260720_0017"
down_revision: str | None = "20260717_0016"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("issues") as batch_op:
        batch_op.add_column(sa.Column("jira_assignee_id", sa.String(length=128), nullable=True))
    with op.batch_alter_table("sprint_metric_snapshots") as batch_op:
        batch_op.add_column(sa.Column("workload_concentration_pct", sa.Float(), nullable=True))
        batch_op.add_column(sa.Column("workload_distribution_status", sa.String(length=32), nullable=True))
        batch_op.add_column(sa.Column("workload_distribution_explanations", sa.JSON(), nullable=True))
        batch_op.add_column(sa.Column("workload_distribution_evidence", sa.JSON(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("sprint_metric_snapshots") as batch_op:
        batch_op.drop_column("workload_distribution_evidence")
        batch_op.drop_column("workload_distribution_explanations")
        batch_op.drop_column("workload_distribution_status")
        batch_op.drop_column("workload_concentration_pct")
    with op.batch_alter_table("issues") as batch_op:
        batch_op.drop_column("jira_assignee_id")
