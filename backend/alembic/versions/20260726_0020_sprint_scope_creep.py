"""Persist the authoritative sprint scope-creep metric.

Revision ID: 20260726_0020
Revises: 20260724_0019
Create Date: 2026-07-26 00:20:00
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260726_0020"
down_revision: str | None = "20260724_0019"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("sprint_metric_snapshots") as batch_op:
        batch_op.add_column(sa.Column("scope_creep_pct", sa.Float(), nullable=True))
        batch_op.add_column(
            sa.Column(
                "scope_creep_status",
                sa.String(length=32),
                nullable=False,
                server_default="NOT_COMPUTED",
            )
        )
        batch_op.add_column(sa.Column("scope_creep_explanations", sa.JSON(), nullable=True))
        batch_op.add_column(sa.Column("scope_creep_evidence", sa.JSON(), nullable=True))

    with op.batch_alter_table("sprint_metric_snapshots") as batch_op:
        batch_op.alter_column("scope_creep_status", server_default=None)


def downgrade() -> None:
    with op.batch_alter_table("sprint_metric_snapshots") as batch_op:
        batch_op.drop_column("scope_creep_evidence")
        batch_op.drop_column("scope_creep_explanations")
        batch_op.drop_column("scope_creep_status")
        batch_op.drop_column("scope_creep_pct")
