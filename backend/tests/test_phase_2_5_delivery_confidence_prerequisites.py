from collections.abc import Generator
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.models import Issue, IssueSprint, Sprint
from app.services.analytics_service import AnalyticsService


@pytest.fixture
def db_session() -> Generator[Session, None, None]:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(bind=engine, class_=Session)
    Base.metadata.create_all(bind=engine)
    with TestingSessionLocal() as session:
        yield session


def _sprint(
    sprint_id: str = "10",
    *,
    state: str = "active",
    start_date: datetime | None = None,
    end_date: datetime | None = None,
    use_default_dates: bool = True,
) -> Sprint:
    now = datetime.now(UTC)
    return Sprint(
        sprint_id=sprint_id,
        name=f"Sprint {sprint_id}",
        state=state,
        project_key="LHPM",
        board_id="1",
        start_date=(start_date or now - timedelta(days=7)) if use_default_dates else start_date,
        end_date=(end_date or now + timedelta(days=7)) if use_default_dates else end_date,
        complete_date=end_date if state == "closed" else None,
        goal=None,
    )


def _issue(
    issue_key: str,
    *,
    status: str | None = "To Do",
    story_points: float | None = 3,
    issue_type: str | None = "Story",
    priority: str | None = "Medium",
    history_complete: bool = True,
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
        is_blocker=False,
        jira_blocker_flag=None,
        jira_changelog_complete=history_complete,
    )


def _link(issue_key: str, sprint_id: str = "10") -> IssueSprint:
    return IssueSprint(issue_key=issue_key, sprint_id=sprint_id)


def test_missing_non_point_inputs_are_inconclusive_with_sorted_evidence(
    db_session: Session,
) -> None:
    db_session.add(_sprint(use_default_dates=False))
    db_session.add(_issue("LHPM-2", status=None))
    db_session.add(_issue("LHPM-1", status="To Do"))
    db_session.add(_issue("LHPM-9", story_points=None, history_complete=False))
    db_session.add_all([_link("LHPM-2"), _link("LHPM-1")])
    db_session.flush()

    snapshot = AnalyticsService().recompute_sprint_metrics(db_session, "10")

    assert snapshot.delivery_confidence_status == "INCONCLUSIVE"
    assert snapshot.delivery_confidence_score is None
    assert snapshot.delivery_confidence_components is None
    assert snapshot.delivery_confidence_inputs is None
    assert snapshot.delivery_confidence_explanations == [
        "Delivery confidence is inconclusive because pointed current-sprint tickets are missing status: LHPM-2.",
        "Delivery confidence is inconclusive because blocker classification is incomplete for current-sprint tickets: LHPM-2.",
        "Delivery confidence is inconclusive because sprint duration requires both a start time and an end time.",
        "Delivery confidence is inconclusive because sprint-membership changelog history is incomplete for synchronized project tickets: LHPM-9.",
    ]
    prerequisites = snapshot.calculation_provenance["delivery_confidence_prerequisites"]
    assert prerequisites["missing_issue_keys"] == ["LHPM-2", "LHPM-9"]
    assert prerequisites["evidence"]["project_issue_keys"] == [
        "LHPM-1",
        "LHPM-2",
        "LHPM-9",
    ]
    availability = snapshot.calculation_provenance["availability"]["metrics"][
        "delivery_confidence_score"
    ]
    assert availability["status"] == "NOT_COMPUTED"
    assert availability["available"] is False
    assert availability["missing_issue_keys"] == ["LHPM-2", "LHPM-9"]


def test_incomplete_blocker_classification_withholds_confidence_only(
    db_session: Session,
) -> None:
    db_session.add(_sprint())
    db_session.add(_issue("LHPM-1", story_points=3))
    db_session.add(
        _issue(
            "LHPM-2",
            story_points=None,
            issue_type=None,
            priority=None,
        )
    )
    db_session.add_all([_link("LHPM-1"), _link("LHPM-2")])
    db_session.flush()

    snapshot = AnalyticsService().recompute_sprint_metrics(db_session, "10")

    assert snapshot.story_point_coverage_pct == 50.0
    assert snapshot.delivery_confidence_status == "INCONCLUSIVE"
    assert snapshot.delivery_confidence_score is None
    assert snapshot.open_blockers == 0
    blocker_availability = snapshot.calculation_provenance["availability"]["metrics"][
        "open_blockers"
    ]
    assert blocker_availability["status"] == "PARTIAL"
    assert blocker_availability["available"] is True
    assert blocker_availability["missing_issue_keys"] == ["LHPM-2"]


@pytest.mark.parametrize(
    ("start_date", "end_date", "reason_fragment"),
    [
        (None, datetime.now(UTC), "missing its start time"),
        (datetime.now(UTC), None, "missing its end time"),
        (datetime.now(UTC), datetime.now(UTC) - timedelta(days=1), "end time must be later"),
    ],
)
def test_missing_or_invalid_duration_never_uses_time_fallbacks(
    db_session: Session,
    start_date: datetime | None,
    end_date: datetime | None,
    reason_fragment: str,
) -> None:
    db_session.add(
        _sprint(
            start_date=start_date,
            end_date=end_date,
            use_default_dates=False,
        )
    )
    db_session.add(_issue("LHPM-1", status="Done"))
    db_session.add(_link("LHPM-1"))
    db_session.flush()

    snapshot = AnalyticsService().recompute_sprint_metrics(db_session, "10")

    assert snapshot.delivery_confidence_status == "INCONCLUSIVE"
    assert snapshot.delivery_confidence_score is None
    assert snapshot.delivery_confidence_components is None
    assert snapshot.delivery_confidence_inputs is None
    assert any(reason_fragment in item for item in snapshot.delivery_confidence_explanations)


def test_partial_story_point_coverage_still_scores_when_prerequisites_are_complete(
    db_session: Session,
) -> None:
    db_session.add(_sprint())
    db_session.add(_issue("LHPM-1", status="Done", story_points=3))
    db_session.add(_issue("LHPM-2", status="To Do", story_points=None))
    db_session.add_all([_link("LHPM-1"), _link("LHPM-2")])
    db_session.flush()

    snapshot = AnalyticsService().recompute_sprint_metrics(db_session, "10")

    assert snapshot.story_point_coverage_pct == 50.0
    assert snapshot.delivery_confidence_status == "PARTIAL"
    assert snapshot.delivery_confidence_score is not None
    assert snapshot.delivery_confidence_components is not None
    assert snapshot.delivery_confidence_inputs is not None


def test_partial_velocity_baseline_marks_complete_current_scope_partial(
    db_session: Session,
) -> None:
    now = datetime.now(UTC)
    target_start = now - timedelta(days=7)
    db_session.add(
        _sprint(
            start_date=target_start,
            end_date=now + timedelta(days=7),
        )
    )
    db_session.add(_issue("LHPM-1", status="To Do", story_points=5))
    db_session.add(_link("LHPM-1"))

    baseline_end = target_start - timedelta(days=1)
    db_session.add(
        _sprint(
            "9",
            state="closed",
            start_date=baseline_end - timedelta(days=14),
            end_date=baseline_end,
        )
    )
    db_session.add(_issue("LHPM-8", status="Done", story_points=5))
    db_session.add(_issue("LHPM-9", status="Done", story_points=None))
    db_session.add_all([_link("LHPM-8", "9"), _link("LHPM-9", "9")])
    db_session.flush()

    snapshot = AnalyticsService().recompute_sprint_metrics(db_session, "10")

    assert snapshot.story_point_coverage_pct == 100.0
    assert snapshot.delivery_confidence_score is not None
    assert snapshot.delivery_confidence_status == "PARTIAL"
    assert snapshot.delivery_confidence_inputs is not None
    assert snapshot.delivery_confidence_inputs["velocity_status"] == "PARTIAL"
    assert any("Historical velocity is partial" in item for item in snapshot.delivery_confidence_explanations)
