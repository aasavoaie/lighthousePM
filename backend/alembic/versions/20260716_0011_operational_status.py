"""Adopt the operational status table into Alembic management.

Revision ID: 20260716_0011
Revises: 20260716_0010
Create Date: 2026-07-16 00:11:00
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260716_0011"
down_revision: str | None = "20260716_0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    schema = sa.inspect(op.get_bind())
    if schema.has_table("operational_status"):
        return

    op.create_table(
        "operational_status",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("last_sync_succeeded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_sync_failed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_sync_failure_summary", sa.String(length=500), nullable=True),
        sa.Column("last_metrics_recompute_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_signal_recompute_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_operational_status"),
    )


def downgrade() -> None:
    # The table predates Alembic adoption in deployed databases. Keep it to
    # avoid deleting operational history during a schema downgrade.
    pass
