"""Add delivery confidence score fields.

Revision ID: 20260427_0004
Revises: 20260425_0003
Create Date: 2026-04-27 00:04:00
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260427_0004"
down_revision: str | None = "20260425_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("issues", sa.Column("story_points", sa.Float(), nullable=True))
    op.add_column(
        "sprint_metric_snapshots",
        sa.Column("delivery_confidence_score", sa.Float(), nullable=True),
    )
    op.add_column(
        "sprint_metric_snapshots",
        sa.Column("delivery_confidence_components", sa.JSON(), nullable=True),
    )
    op.add_column(
        "sprint_metric_snapshots",
        sa.Column("delivery_confidence_inputs", sa.JSON(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("sprint_metric_snapshots", "delivery_confidence_inputs")
    op.drop_column("sprint_metric_snapshots", "delivery_confidence_components")
    op.drop_column("sprint_metric_snapshots", "delivery_confidence_score")
    op.drop_column("issues", "story_points")
