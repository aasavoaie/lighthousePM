"""Persist sprint story-point coverage and delivery-confidence status.

Revision ID: 20260716_0008
Revises: 20260430_0007
Create Date: 2026-07-16 00:08:00
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260716_0008"
down_revision: str | None = "20260430_0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "sprint_metric_snapshots",
        sa.Column("story_point_total_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "sprint_metric_snapshots",
        sa.Column("story_point_pointed_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "sprint_metric_snapshots",
        sa.Column("story_point_unpointed_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "sprint_metric_snapshots",
        sa.Column("story_point_coverage_pct", sa.Float(), nullable=False, server_default="0"),
    )
    op.add_column(
        "sprint_metric_snapshots",
        sa.Column(
            "story_point_unpointed_issue_keys",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'[]'"),
        ),
    )
    op.add_column(
        "sprint_metric_snapshots",
        sa.Column(
            "delivery_confidence_status",
            sa.String(length=32),
            nullable=False,
            server_default="NOT_COMPUTED",
        ),
    )
    op.add_column(
        "sprint_metric_snapshots",
        sa.Column(
            "delivery_confidence_explanations",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'[]'"),
        ),
    )

    if op.get_bind().dialect.name != "sqlite":
        for column_name in (
            "story_point_total_count",
            "story_point_pointed_count",
            "story_point_unpointed_count",
            "story_point_coverage_pct",
            "story_point_unpointed_issue_keys",
            "delivery_confidence_status",
            "delivery_confidence_explanations",
        ):
            op.alter_column("sprint_metric_snapshots", column_name, server_default=None)


def downgrade() -> None:
    op.drop_column("sprint_metric_snapshots", "delivery_confidence_explanations")
    op.drop_column("sprint_metric_snapshots", "delivery_confidence_status")
    op.drop_column("sprint_metric_snapshots", "story_point_unpointed_issue_keys")
    op.drop_column("sprint_metric_snapshots", "story_point_coverage_pct")
    op.drop_column("sprint_metric_snapshots", "story_point_unpointed_count")
    op.drop_column("sprint_metric_snapshots", "story_point_pointed_count")
    op.drop_column("sprint_metric_snapshots", "story_point_total_count")
