"""Add release completed tickets metric.

Revision ID: 20260429_0006
Revises: 20260428_0005
Create Date: 2026-04-29 00:06:00
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260429_0006"
down_revision: str | None = "20260428_0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("metric_snapshots", sa.Column("completed_tickets", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("metric_snapshots", "completed_tickets")
