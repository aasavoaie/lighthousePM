"""Add immutable ruleset provenance and append-only signal evidence.

Revision ID: 20260716_0010
Revises: 20260716_0009
Create Date: 2026-07-16 00:10:00
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260716_0010"
down_revision: str | None = "20260716_0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    for table_name in ("metric_snapshots", "sprint_metric_snapshots"):
        op.add_column(
            table_name,
            sa.Column("ruleset_version", sa.Integer(), nullable=False, server_default="0"),
        )
        op.add_column(
            table_name,
            sa.Column(
                "calculation_provenance",
                sa.JSON(),
                nullable=False,
                server_default=sa.text("'{}'"),
            ),
        )

    op.add_column("metric_snapshots", sa.Column("confidence_score", sa.Float(), nullable=True))
    op.add_column("metric_snapshots", sa.Column("confidence_status", sa.String(length=32), nullable=True))

    with op.batch_alter_table("release_signals") as batch_op:
        batch_op.add_column(sa.Column("metric_snapshot_id", sa.Integer(), nullable=True))
        batch_op.add_column(
            sa.Column("ruleset_version", sa.Integer(), nullable=False, server_default="0")
        )
        batch_op.add_column(sa.Column("confidence_score", sa.Float(), nullable=True))
        batch_op.add_column(
            sa.Column("reason_details", sa.JSON(), nullable=False, server_default=sa.text("'[]'"))
        )
        batch_op.add_column(
            sa.Column("release_gates", sa.JSON(), nullable=False, server_default=sa.text("'[]'"))
        )
        batch_op.add_column(
            sa.Column("readiness_evidence", sa.JSON(), nullable=False, server_default=sa.text("'{}'"))
        )
        batch_op.add_column(
            sa.Column("risk_aging_evidence", sa.JSON(), nullable=False, server_default=sa.text("'{}'"))
        )
        batch_op.add_column(
            sa.Column(
                "calculated_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.func.now(),
            )
        )
        batch_op.create_foreign_key(
            "fk_release_signals_metric_snapshot_id",
            "metric_snapshots",
            ["metric_snapshot_id"],
            ["id"],
            ondelete="CASCADE",
        )
        batch_op.create_unique_constraint(
            "uq_release_signal_snapshot_ruleset",
            ["release_id", "metric_snapshot_id", "ruleset_version"],
        )


def downgrade() -> None:
    with op.batch_alter_table("release_signals") as batch_op:
        batch_op.drop_constraint("uq_release_signal_snapshot_ruleset", type_="unique")
        batch_op.drop_constraint("fk_release_signals_metric_snapshot_id", type_="foreignkey")
        batch_op.drop_column("calculated_at")
        batch_op.drop_column("risk_aging_evidence")
        batch_op.drop_column("readiness_evidence")
        batch_op.drop_column("release_gates")
        batch_op.drop_column("reason_details")
        batch_op.drop_column("confidence_score")
        batch_op.drop_column("ruleset_version")
        batch_op.drop_column("metric_snapshot_id")

    op.drop_column("metric_snapshots", "confidence_status")
    op.drop_column("metric_snapshots", "confidence_score")
    for table_name in ("sprint_metric_snapshots", "metric_snapshots"):
        op.drop_column(table_name, "calculation_provenance")
        op.drop_column(table_name, "ruleset_version")
