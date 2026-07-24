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
    project_key: str = "LHPM",
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
        project_key=project_key,
        board_id="1",
        start_date=(start_date if start_date is not None else now - timedelta(days=7)) if with_dates else None,
        end_date=(end_date if end_date is not None else now + timedelta(days=7)) if with_dates else None,
        complete_date=complete_date if complete_date is not None else (now if state == "closed" else None),
        goal=None,
    )


def _issue(
    issue_key: str,
    status: str | None,
    issue_type: str = "Story",
    priority: str | None = "Medium",
    story_points: float | None = None,
    created_at: datetime | None = None,
) -> Issue:
    source_created_at = created_at or datetime.now(UTC)
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
        jira_created_at=source_created_at,
        jira_changelog_complete=True,
        created_at=source_created_at,
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
    assert snapshot.bugs_created_during_sprint == 1
    assert snapshot.open_blocker_issue_keys == ["LHPM-3"]
    assert snapshot.open_high_severity_bug_issue_keys == ["LHPM-2"]
    assert snapshot.bugs_created_during_sprint_issue_keys == ["LHPM-2"]
    assert snapshot.in_progress_count == 1
    assert snapshot.not_started_count == 1
    assert snapshot.rollover_count is None
    assert snapshot.calculation_provenance["availability"]["metrics"]["rollover_count"][
        "status"
    ] == "NOT_APPLICABLE"
    assert snapshot.delivery_confidence_score is None


def test_recompute_sprint_metrics_counts_closed_sprint_rollover(db_session: Session) -> None:
    db_session.add(_sprint(state="closed"))
    db_session.add(_issue("LHPM-1", "Done"))
    db_session.add(_issue("LHPM-2", "In Progress"))
    db_session.add(_issue("LHPM-3", "To Do"))
    db_session.add_all([_link("LHPM-1"), _link("LHPM-2"), _link("LHPM-3")])
    db_session.flush()

    snapshot = AnalyticsService().recompute_sprint_metrics(db_session, "10")

    assert snapshot.rollover_count == 2


def test_recompute_sprint_metrics_counts_bugs_created_during_sprint(db_session: Session) -> None:
    base = datetime(2026, 4, 1, tzinfo=UTC)
    db_session.add(_sprint(start_date=base, end_date=base + timedelta(days=14)))
    db_session.add(_issue("LHPM-1", "To Do", issue_type="Bug", created_at=base))
    db_session.add(_issue("LHPM-2", "Done", issue_type="Bug", created_at=base + timedelta(days=3)))
    db_session.add(_issue("LHPM-3", "To Do", issue_type="Bug", created_at=base - timedelta(seconds=1)))
    db_session.add(_issue("LHPM-4", "To Do", issue_type="Bug", created_at=base + timedelta(days=15)))
    db_session.add(_issue("LHPM-5", "To Do", issue_type="Story", created_at=base + timedelta(days=2)))
    db_session.add_all([_link(f"LHPM-{index}") for index in range(1, 6)])
    db_session.flush()

    snapshot = AnalyticsService().recompute_sprint_metrics(db_session, "10")

    assert snapshot.bugs_created_during_sprint == 2
    assert snapshot.bugs_created_during_sprint_issue_keys == ["LHPM-1", "LHPM-2"]


def test_recompute_sprint_metrics_cycle_time_and_reopen_rate(db_session: Session) -> None:
    base = datetime(2026, 4, 1, tzinfo=UTC)
    db_session.add(_sprint())
    db_session.add(_issue("LHPM-1", "Done"))
    db_session.add(_issue("LHPM-2", "In Progress"))
    db_session.add_all([_link("LHPM-1"), _link("LHPM-2")])
    db_session.flush()
    db_session.add(_history("LHPM-1", "To Do", "In Progress", base))
    db_session.add(_history("LHPM-1", "In Progress", "Done", base + timedelta(days=3)))
    db_session.add(_history("LHPM-2", "To Do", "Done", base + timedelta(days=3, hours=1)))
    db_session.add(_history("LHPM-2", "Done", "In Progress", base + timedelta(days=4)))
    db_session.flush()

    snapshot = AnalyticsService().recompute_sprint_metrics(db_session, "10")
    db_session.commit()

    stored = db_session.scalar(select(SprintMetricSnapshot).where(SprintMetricSnapshot.sprint_id == "10"))
    assert stored is not None
    assert snapshot.median_cycle_time_days == 3
    assert snapshot.reopen_rate_pct == 50.0
    assert snapshot.calculation_provenance["availability"]["metrics"][
        "median_cycle_time_days"
    ]["status"] == "COMPUTED"
    assert snapshot.calculation_provenance["availability"]["metrics"][
        "reopen_rate_pct"
    ]["status"] == "COMPUTED"
    assert snapshot.calculation_provenance["metric_evidence"]["reopen_rate_pct"][
        "eligible_ticket_count"
    ] == 2


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
    db_session.add(_sprint(sprint_id="10"))
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
    assert snapshot.delivery_confidence_components["velocity_fit"] == 25.0


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
    assert snapshot.delivery_confidence_components["scope_stability"] == 0.0
    assert snapshot.delivery_confidence_inputs["initial_commitment_count"] == 1
    assert snapshot.delivery_confidence_inputs["scope_added_count"] == 1
    assert snapshot.delivery_confidence_inputs["scope_removed_count"] == 0
    assert snapshot.delivery_confidence_inputs["scope_stability_index"] == 1.0
    assert snapshot.delivery_confidence_inputs["scope_change_issue_keys"] == ["LHPM-1"]
    assert snapshot.delivery_confidence_inputs["scope_added_issue_keys"] == ["LHPM-1"]
    assert snapshot.delivery_confidence_inputs["scope_removed_issue_keys"] == []


def test_scope_stability_index_counts_added_and_removed_issues(db_session: Session) -> None:
    now = datetime.now(UTC)
    db_session.add(_sprint(start_date=now - timedelta(days=2), end_date=now + timedelta(days=2)))
    db_session.add(_issue("LHPM-1", "In Progress", story_points=3))
    db_session.add(_issue("LHPM-2", "To Do", story_points=0))
    db_session.add(_issue("LHPM-3", "To Do"))
    db_session.add(_issue("LHPM-4", "To Do"))
    db_session.add_all([_link("LHPM-1"), _link("LHPM-2"), _link("LHPM-3")])
    db_session.flush()
    db_session.add(
        _history(
            "LHPM-3",
            old_value="Sprint 9",
            new_value="Sprint 10",
            changed_at=now - timedelta(days=1),
            field_name="sprint",
        )
    )
    db_session.add(
        _history(
            "LHPM-4",
            old_value="Sprint 10",
            new_value="Sprint 11",
            changed_at=now - timedelta(hours=12),
            field_name="sprint",
        )
    )
    db_session.flush()

    snapshot = AnalyticsService().recompute_sprint_metrics(db_session, "10")

    assert snapshot.delivery_confidence_inputs is not None
    assert snapshot.delivery_confidence_inputs["initial_commitment_count"] == 3
    assert snapshot.delivery_confidence_inputs["scope_added_count"] == 1
    assert snapshot.delivery_confidence_inputs["scope_removed_count"] == 1
    assert snapshot.delivery_confidence_inputs["scope_change_count"] == 2
    assert snapshot.delivery_confidence_inputs["scope_stability_index"] == 0.6667
    assert snapshot.delivery_confidence_inputs["scope_change_issue_keys"] == ["LHPM-3", "LHPM-4"]
    assert snapshot.delivery_confidence_inputs["scope_added_issue_keys"] == ["LHPM-3"]
    assert snapshot.delivery_confidence_inputs["scope_removed_issue_keys"] == ["LHPM-4"]


def test_scope_stability_ignores_same_sprint_reference_from_other_project(db_session: Session) -> None:
    now = datetime.now(UTC)
    db_session.add(_sprint(start_date=now - timedelta(days=2), end_date=now + timedelta(days=2)))
    db_session.add(_issue("LHPM-1", "In Progress", story_points=3))
    db_session.add(_issue("OTHER-1", "In Progress"))
    db_session.add(_link("LHPM-1"))
    db_session.flush()
    db_session.add(
        _history(
            "OTHER-1",
            old_value="Sprint 9",
            new_value="Sprint 10",
            changed_at=now - timedelta(days=1),
            field_name="sprint",
        )
    )
    db_session.flush()

    snapshot = AnalyticsService().recompute_sprint_metrics(db_session, "10")

    assert snapshot.delivery_confidence_inputs is not None
    assert snapshot.delivery_confidence_inputs["scope_added_count"] == 0
    assert snapshot.delivery_confidence_inputs["scope_removed_count"] == 0
    assert snapshot.delivery_confidence_inputs["scope_change_issue_keys"] == []


def test_delivery_confidence_empty_sprint_is_not_computed(db_session: Session) -> None:
    db_session.add(_sprint())
    db_session.flush()

    snapshot = AnalyticsService().recompute_sprint_metrics(db_session, "10")

    assert snapshot.delivery_confidence_score is None
    assert snapshot.delivery_confidence_components is None
    assert snapshot.delivery_confidence_inputs is None
    assert snapshot.delivery_confidence_status == "NOT_COMPUTED"
    assert snapshot.story_point_total_count == 0
    assert snapshot.story_point_coverage_pct == 0.0


def test_delivery_confidence_uses_only_story_points_when_some_issues_are_missing_points(db_session: Session) -> None:
    db_session.add(_sprint())
    db_session.add(_issue("LHPM-1", "Done", story_points=3))
    db_session.add(_issue("LHPM-2", "To Do", story_points=None))
    db_session.add_all([_link("LHPM-1"), _link("LHPM-2")])
    db_session.flush()

    snapshot = AnalyticsService().recompute_sprint_metrics(db_session, "10")

    assert snapshot.delivery_confidence_inputs is not None
    assert snapshot.delivery_confidence_inputs["committed_effective_points"] == 3.0
    assert snapshot.delivery_confidence_inputs["completed_effective_points"] == 3.0
    assert snapshot.delivery_confidence_inputs["remaining_effective_points"] == 0.0
    assert snapshot.delivery_confidence_components is not None
    assert snapshot.delivery_confidence_components["progress_alignment"] == 100.0
    assert snapshot.delivery_confidence_components["velocity_fit"] == 100.0
    assert snapshot.delivery_confidence_status == "PARTIAL"
    assert snapshot.story_point_pointed_count == 1
    assert snapshot.story_point_unpointed_count == 1
    assert snapshot.story_point_coverage_pct == 50.0
    assert snapshot.story_point_unpointed_issue_keys == ["LHPM-2"]
    assert len(snapshot.delivery_confidence_explanations) >= 2


def test_delivery_confidence_is_inconclusive_below_half_coverage(db_session: Session) -> None:
    db_session.add(_sprint())
    db_session.add(_issue("LHPM-1", "Done", story_points=3))
    db_session.add(_issue("LHPM-2", "To Do", story_points=None))
    db_session.add(_issue("LHPM-3", "To Do", story_points=-1))
    db_session.add_all([_link("LHPM-1"), _link("LHPM-2"), _link("LHPM-3")])
    db_session.flush()

    snapshot = AnalyticsService().recompute_sprint_metrics(db_session, "10")

    assert snapshot.delivery_confidence_status == "INCONCLUSIVE"
    assert snapshot.delivery_confidence_score is None
    assert snapshot.delivery_confidence_components is None
    assert snapshot.delivery_confidence_inputs is None
    assert snapshot.story_point_coverage_pct == 33.33
    assert snapshot.story_point_unpointed_issue_keys == ["LHPM-2", "LHPM-3"]
    assert "fewer than 50%" in snapshot.delivery_confidence_explanations[0]
    assert snapshot.calculation_provenance["metric_evidence"]["committed_scope"] == {
        "current_scope_issue_keys": ["LHPM-1", "LHPM-2", "LHPM-3"],
        "current_scope_count": 3,
    }
    assert snapshot.calculation_provenance["metric_evidence"]["completed_scope_pct"][
        "completed_issue_keys"
    ] == ["LHPM-1"]


def test_recompute_sprint_metrics_persists_unavailable_empty_scope(
    db_session: Session,
) -> None:
    db_session.add(_sprint())
    db_session.flush()

    snapshot = AnalyticsService().recompute_sprint_metrics(db_session, "10")

    assert snapshot.committed_scope is None
    assert snapshot.completed_scope_pct is None
    assert snapshot.in_progress_count is None
    assert snapshot.not_started_count is None
    assert snapshot.rollover_count is None
    availability = snapshot.calculation_provenance["availability"]["metrics"]
    assert availability["committed_scope"]["status"] == "NOT_COMPUTED"
    assert availability["completed_scope_pct"]["status"] == "NOT_COMPUTED"
    assert availability["in_progress_count"]["status"] == "NOT_COMPUTED"
    assert availability["not_started_count"]["status"] == "NOT_COMPUTED"
    assert availability["rollover_count"]["status"] == "NOT_APPLICABLE"
    assert snapshot.calculation_provenance["metric_evidence"]["committed_scope"] == {
        "current_scope_issue_keys": [],
        "current_scope_count": 0,
    }


def test_recompute_sprint_metrics_persists_partial_completed_scope(
    db_session: Session,
) -> None:
    db_session.add(_sprint())
    db_session.add_all([_issue("LHPM-1", "Done"), _issue("LHPM-2", None)])
    db_session.add_all([_link("LHPM-1"), _link("LHPM-2")])
    db_session.flush()

    snapshot = AnalyticsService().recompute_sprint_metrics(db_session, "10")

    assert snapshot.committed_scope == 2
    assert snapshot.completed_scope_pct is None
    assert snapshot.in_progress_count == 0
    assert snapshot.not_started_count == 0
    assert snapshot.rollover_count is None
    availability = snapshot.calculation_provenance["availability"]["metrics"]
    assert availability["committed_scope"]["status"] == "COMPUTED"
    assert availability["completed_scope_pct"]["status"] == "PARTIAL"
    assert availability["completed_scope_pct"]["missing_issue_keys"] == ["LHPM-2"]
    assert availability["in_progress_count"]["status"] == "PARTIAL"
    assert availability["in_progress_count"]["available"] is True
    assert availability["not_started_count"]["status"] == "PARTIAL"
    assert availability["rollover_count"]["status"] == "NOT_APPLICABLE"
    assert snapshot.calculation_provenance["metric_evidence"]["in_progress_count"][
        "missing_status_issue_keys"
    ] == ["LHPM-2"]
