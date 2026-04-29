from collections.abc import Generator
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.models import Issue, IssueHistory, IssueSprint, Sprint, SprintMetricSnapshot
from app.services.analytics_service import AnalyticsService


@pytest.fixture
def db_session() -> Generator[Session, None, None]:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, class_=Session)
    Base.metadata.create_all(bind=engine)
    with TestingSessionLocal() as session:
        yield session


def _sprint(
    sprint_id: str = "10",
    state: str = "active",
    name: str | None = None,
    start_date: datetime | None = None,
    end_date: datetime | None = None,
    complete_date: datetime | None = None,
    with_dates: bool = True,
) -> Sprint:
    now = datetime.now(UTC)
    return Sprint(
        sprint_id=sprint_id,
        name=name or f"Sprint {sprint_id}",
        state=state,
        project_key="LHPM",
        board_id="1",
        start_date=(start_date if start_date is not None else now - timedelta(days=7)) if with_dates else None,
        end_date=(end_date if end_date is not None else now + timedelta(days=7)) if with_dates else None,
        complete_date=complete_date if complete_date is not None else (now if state == "closed" else None),
        goal=None,
    )


def _issue(
    issue_key: str,
    status: str,
    issue_type: str = "Story",
    priority: str | None = "Medium",
    story_points: float | None = None,
) -> Issue:
    return Issue(
        issue_key=issue_key,
        summary=f"{issue_key} summary",
        issue_type=issue_type,
        status=status,
        priority=priority,
        assignee=None,
        story_points=story_points,
        release_id=None,
        is_blocker=priority == "Blocker",
    )


def _link(issue_key: str, sprint_id: str = "10") -> IssueSprint:
    return IssueSprint(issue_key=issue_key, sprint_id=sprint_id)


def _history(
    issue_key: str,
    old_value: str,
    new_value: str,
    changed_at: datetime,
    field_name: str = "status",
) -> IssueHistory:
    return IssueHistory(
        issue_key=issue_key,
        field_name=field_name,
        old_value=old_value,
        new_value=new_value,
        changed_at=changed_at,
    )


def test_recompute_sprint_metrics_counts_status_buckets(db_session: Session) -> None:
    db_session.add(_sprint())
    db_session.add(_issue("LHPM-1", "Done"))
    db_session.add(_issue("LHPM-2", "In Progress", issue_type="Bug", priority="High"))
    db_session.add(_issue("LHPM-3", "To Do", priority="Blocker"))
    db_session.add_all([_link("LHPM-1"), _link("LHPM-2"), _link("LHPM-3")])
    db_session.flush()

    snapshot = AnalyticsService().recompute_sprint_metrics(db_session, "10")

    assert snapshot.committed_scope == 3
    assert snapshot.completed_scope_pct == 33.33
    assert snapshot.open_blockers == 1
    assert snapshot.open_high_severity_bugs == 1
    assert snapshot.open_blocker_issue_keys == ["LHPM-3"]
    assert snapshot.open_high_severity_bug_issue_keys == ["LHPM-2"]
    assert snapshot.in_progress_count == 1
    assert snapshot.not_started_count == 1
    assert snapshot.rollover_count == 0
    assert snapshot.delivery_confidence_score is not None


def test_recompute_sprint_metrics_counts_closed_sprint_rollover(db_session: Session) -> None:
    db_session.add(_sprint(state="closed"))
    db_session.add(_issue("LHPM-1", "Done"))
    db_session.add(_issue("LHPM-2", "In Progress"))
    db_session.add(_issue("LHPM-3", "To Do"))
    db_session.add_all([_link("LHPM-1"), _link("LHPM-2"), _link("LHPM-3")])
    db_session.flush()

    snapshot = AnalyticsService().recompute_sprint_metrics(db_session, "10")

    assert snapshot.rollover_count == 2


def test_recompute_sprint_metrics_cycle_time_and_reopen_rate(db_session: Session) -> None:
    base = datetime(2026, 4, 1, tzinfo=UTC)
    db_session.add(_sprint())
    db_session.add(_issue("LHPM-1", "Done"))
    db_session.add(_issue("LHPM-2", "In Progress"))
    db_session.add_all([_link("LHPM-1"), _link("LHPM-2")])
    db_session.flush()
    db_session.add(_history("LHPM-1", "To Do", "In Progress", base))
    db_session.add(_history("LHPM-1", "In Progress", "Done", base + timedelta(days=3)))
    db_session.add(_history("LHPM-2", "Done", "In Progress", base + timedelta(days=4)))
    db_session.flush()

    snapshot = AnalyticsService().recompute_sprint_metrics(db_session, "10")
    db_session.commit()

    stored = db_session.scalar(select(SprintMetricSnapshot).where(SprintMetricSnapshot.sprint_id == "10"))
    assert stored is not None
    assert snapshot.median_cycle_time_days == 3
    assert snapshot.reopen_rate_pct == 50.0


def test_recompute_sprint_metrics_raises_for_unknown_sprint(db_session: Session) -> None:
    with pytest.raises(ValueError, match="Sprint not found"):
        AnalyticsService().recompute_sprint_metrics(db_session, "missing")


def test_delivery_confidence_perfect_when_done_and_stable(db_session: Session) -> None:
    db_session.add(_sprint())
    db_session.add(_issue("LHPM-1", "Done", story_points=8))
    db_session.add(_issue("LHPM-2", "Done", story_points=5))
    db_session.add_all([_link("LHPM-1"), _link("LHPM-2")])
    db_session.flush()

    snapshot = AnalyticsService().recompute_sprint_metrics(db_session, "10")

    assert snapshot.delivery_confidence_score == 100.0
    assert snapshot.delivery_confidence_components == {
        "progress_alignment": 100.0,
        "velocity_fit": 100.0,
        "blocker_penalty": 100.0,
        "scope_stability": 100.0,
    }


def test_delivery_confidence_uses_last_three_closed_sprints_for_velocity(db_session: Session) -> None:
    base = datetime(2026, 4, 20, tzinfo=UTC)
    db_session.add(_sprint(sprint_id="10", with_dates=False))
    db_session.add(_issue("LHPM-1", "To Do", story_points=20))
    db_session.add(_link("LHPM-1"))

    for index, points in enumerate([100, 10, 10, 10], start=1):
        sprint_id = str(index)
        complete_date = base - timedelta(days=5 - index)
        db_session.add(
            _sprint(
                sprint_id=sprint_id,
                state="closed",
                start_date=complete_date - timedelta(days=14),
                end_date=complete_date,
                complete_date=complete_date,
            )
        )
        issue_key = f"LHPM-H{index}"
        db_session.add(_issue(issue_key, "Done", story_points=points))
        db_session.add(_link(issue_key, sprint_id=sprint_id))
    db_session.flush()

    snapshot = AnalyticsService().recompute_sprint_metrics(db_session, "10")

    assert snapshot.delivery_confidence_components is not None
    assert snapshot.delivery_confidence_inputs is not None
    assert snapshot.delivery_confidence_inputs["baseline_sprint_count"] == 3
    assert snapshot.delivery_confidence_inputs["historical_velocity"] == 10.0
    assert snapshot.delivery_confidence_components["velocity_fit"] == 50.0


def test_delivery_confidence_penalizes_blockers_and_scope_changes(db_session: Session) -> None:
    now = datetime.now(UTC)
    db_session.add(_sprint(start_date=now - timedelta(days=1), end_date=now + timedelta(days=1)))
    db_session.add(_issue("LHPM-1", "In Progress", priority="Blocker", story_points=3))
    db_session.add(_issue("LHPM-2", "Done", story_points=3))
    db_session.add_all([_link("LHPM-1"), _link("LHPM-2")])
    db_session.flush()
    db_session.add(
        _history(
            "LHPM-1",
            old_value="Sprint 9",
            new_value="Sprint 10",
            changed_at=now - timedelta(hours=6),
            field_name="sprint",
        )
    )
    db_session.flush()

    snapshot = AnalyticsService().recompute_sprint_metrics(db_session, "10")

    assert snapshot.delivery_confidence_components is not None
    assert snapshot.delivery_confidence_inputs is not None
    assert snapshot.delivery_confidence_components["blocker_penalty"] == 50.0
    assert snapshot.delivery_confidence_components["scope_stability"] == 50.0
    assert snapshot.delivery_confidence_inputs["scope_change_issue_keys"] == ["LHPM-1"]


def test_delivery_confidence_empty_sprint_scores_full_confidence(db_session: Session) -> None:
    db_session.add(_sprint())
    db_session.flush()

    snapshot = AnalyticsService().recompute_sprint_metrics(db_session, "10")

    assert snapshot.delivery_confidence_score == 100.0
    assert snapshot.delivery_confidence_inputs is not None
    assert snapshot.delivery_confidence_inputs["committed_effective_points"] == 0.0


def test_delivery_confidence_uses_issue_count_for_missing_story_points(db_session: Session) -> None:
    db_session.add(_sprint(with_dates=False))
    db_session.add(_issue("LHPM-1", "Done", story_points=3))
    db_session.add(_issue("LHPM-2", "To Do", story_points=None))
    db_session.add_all([_link("LHPM-1"), _link("LHPM-2")])
    db_session.flush()

    snapshot = AnalyticsService().recompute_sprint_metrics(db_session, "10")

    assert snapshot.delivery_confidence_inputs is not None
    assert snapshot.delivery_confidence_inputs["committed_effective_points"] == 4.0
    assert snapshot.delivery_confidence_inputs["completed_effective_points"] == 3.0
    assert snapshot.delivery_confidence_inputs["remaining_effective_points"] == 1.0
    assert snapshot.delivery_confidence_components is not None
    assert snapshot.delivery_confidence_components["progress_alignment"] == 100.0
    assert snapshot.delivery_confidence_components["velocity_fit"] == 50.0
