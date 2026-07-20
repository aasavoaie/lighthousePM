from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db.base import Base
from app.models import MetricSnapshot, Release, ReleaseSignal, Sprint, SprintMetricSnapshot
from app.utils.constants import RULESET_VERSION


def test_runtime_ruleset_version_matches_product_catalog() -> None:
    catalog = (Path(__file__).resolve().parents[2] / "PRODUCT_RULES.md").read_text(encoding="utf-8")

    assert RULESET_VERSION == 2
    assert "Version `2` identifies the approved Phase 2 metric-contract hardening" in catalog


def test_derived_results_are_immutable_after_persistence() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    now = datetime.now(UTC)
    with Session(engine) as session:
        session.add(
            Release(
                release_id="REL-1",
                name="Release 1",
                project_key="LHPM",
                description=None,
                status="active",
                start_date=now,
                release_date=None,
                created_at=now,
                updated_at=now,
            )
        )
        release_snapshot = MetricSnapshot(
            release_id="REL-1",
            snapshot_at=now,
            ruleset_version=1,
            confidence_score=72.0,
            confidence_status="COMPUTED",
            calculation_provenance={},
            open_blockers=1,
            open_high_severity_bugs=0,
            open_blocker_issue_keys=["LHPM-1"],
            open_high_severity_bug_issue_keys=[],
            scope_completed_pct=50.0,
            completed_tickets=1,
            scope_churn_7d_pct=0.0,
            scope_added_7d_count=0,
            scope_removed_7d_count=0,
            median_cycle_time_days=2.0,
            reopen_rate_pct=0.0,
        )
        session.add(release_snapshot)
        session.commit()

        release_snapshot.open_blockers = 0
        with pytest.raises(ValueError, match="Metric snapshots are immutable"):
            session.commit()
        session.rollback()

        signal = ReleaseSignal(
            release_id="REL-1",
            metric_snapshot_id=release_snapshot.id,
            ruleset_version=1,
            signal="RED",
            confidence_score=72.0,
            reasons=["Open blocker"],
            reason_details=[],
            release_gates=[],
            readiness_evidence={},
            risk_aging_evidence={},
            calculated_at=now,
        )
        session.add(signal)
        session.commit()

        signal.signal = "GREEN"
        with pytest.raises(ValueError, match="Release signals are immutable"):
            session.commit()
        session.rollback()


def test_legacy_snapshot_defaults_to_ruleset_zero() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    now = datetime.now(UTC)
    with Session(engine) as session:
        session.add(
            Sprint(
                sprint_id="12",
                name="Sprint 12",
                state="active",
                project_key="LHPM",
                board_id="1",
                start_date=now,
                end_date=now,
                complete_date=None,
                goal=None,
            )
        )
        snapshot = SprintMetricSnapshot(
            sprint_id="12",
            snapshot_at=now,
            committed_scope=0,
            completed_scope_pct=0.0,
            open_blockers=0,
            open_high_severity_bugs=0,
            bugs_created_during_sprint=0,
            open_blocker_issue_keys=[],
            open_high_severity_bug_issue_keys=[],
            bugs_created_during_sprint_issue_keys=[],
            bugs_created_during_sprint_status="COMPUTED",
            bugs_created_during_sprint_missing_created_at_issue_keys=[],
            in_progress_count=0,
            not_started_count=0,
            rollover_count=0,
            median_cycle_time_days=None,
            reopen_rate_pct=0.0,
            delivery_confidence_score=None,
            delivery_confidence_components=None,
            delivery_confidence_inputs=None,
            story_point_total_count=0,
            story_point_pointed_count=0,
            story_point_unpointed_count=0,
            story_point_coverage_pct=0.0,
            story_point_unpointed_issue_keys=[],
            delivery_confidence_status="NOT_COMPUTED",
            delivery_confidence_explanations=[],
        )
        session.add(snapshot)
        session.commit()

        assert snapshot.ruleset_version == 0
        assert snapshot.calculation_provenance == {}

        snapshot.committed_scope = 1
        with pytest.raises(ValueError, match="Sprint metric snapshots are immutable"):
            session.commit()
