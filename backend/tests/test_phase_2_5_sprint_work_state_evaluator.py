from collections.abc import Generator
from datetime import UTC, datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.config import Settings
from app.db.base import Base
from app.models import Issue, IssueSprint, Sprint
from app.schemas.availability import (
    MetricAvailability,
    MetricAvailabilityContext,
    MetricAvailabilityItem,
)
from app.services.jira_field_mapper import JiraFieldMapper
from app.services.metric_availability_service import MetricAvailabilityService


@pytest.fixture
def db_session() -> Generator[Session, None, None]:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    testing_session_local = sessionmaker(bind=engine, class_=Session)
    Base.metadata.create_all(bind=engine)
    with testing_session_local() as session:
        yield session


def _field_mapper() -> JiraFieldMapper:
    return JiraFieldMapper(Settings(_env_file=None))


def _sprint(state: str) -> Sprint:
    return Sprint(
        sprint_id="10",
        name="Sprint 10",
        state=state,
        project_key="LHPM",
    )


def _issue(issue_key: str, status: str | None) -> Issue:
    now = datetime.now(UTC)
    return Issue(
        issue_key=issue_key,
        summary=f"{issue_key} summary",
        issue_type="Story",
        status=status,
        priority="Medium",
        assignee=None,
        story_points=None,
        release_id=None,
        is_blocker=False,
        jira_created_at=now,
        jira_changelog_complete=True,
        created_at=now,
    )


def _add_scope(db_session: Session, *issues: Issue) -> None:
    db_session.add_all(issues)
    db_session.add_all(
        IssueSprint(issue_key=issue.issue_key, sprint_id="10")
        for issue in reversed(issues)
    )
    db_session.flush()


def test_active_sprint_counts_work_state_and_marks_unfinished_scope_not_applicable(
    db_session: Session,
) -> None:
    db_session.add(_sprint("active"))
    _add_scope(
        db_session,
        _issue("LHPM-3", "To Do"),
        _issue("LHPM-1", "Done"),
        _issue("LHPM-2", "In Progress"),
    )

    result = MetricAvailabilityService.evaluate_sprint_work_state_metrics(
        db_session,
        "10",
        _field_mapper(),
    )

    assert result["in_progress_count"]["value"] == 1
    assert result["in_progress_count"]["evidence"]["matching_issue_keys"] == [
        "LHPM-2"
    ]
    assert result["not_started_count"]["value"] == 1
    assert result["not_started_count"]["evidence"]["matching_issue_keys"] == [
        "LHPM-3"
    ]
    assert result["rollover_count"]["value"] is None
    assert result["rollover_count"]["status"] == "NOT_APPLICABLE"
    assert result["rollover_count"]["available"] is False
    assert result["rollover_count"]["evidence"]["applicable"] is False


def test_empty_active_sprint_keeps_work_counts_unavailable_and_rollover_not_applicable(
    db_session: Session,
) -> None:
    db_session.add(_sprint("active"))
    db_session.flush()

    result = MetricAvailabilityService.evaluate_sprint_work_state_metrics(
        db_session,
        "10",
        _field_mapper(),
    )

    assert result["in_progress_count"]["value"] is None
    assert result["in_progress_count"]["status"] == "NOT_COMPUTED"
    assert result["not_started_count"]["value"] is None
    assert result["not_started_count"]["status"] == "NOT_COMPUTED"
    assert result["rollover_count"]["status"] == "NOT_APPLICABLE"


def test_closed_sprint_counts_known_unfinished_tickets(db_session: Session) -> None:
    db_session.add(_sprint(" CLOSED "))
    _add_scope(
        db_session,
        _issue("LHPM-4", "Closed"),
        _issue("LHPM-2", "In Review"),
        _issue("LHPM-3", "To Do"),
        _issue("LHPM-1", "Done"),
    )

    result = MetricAvailabilityService.evaluate_sprint_work_state_metrics(
        db_session,
        "10",
        _field_mapper(),
    )

    assert result["rollover_count"]["value"] == 2
    assert result["rollover_count"]["status"] == "COMPUTED"
    assert result["rollover_count"]["evidence"]["unfinished_issue_keys"] == [
        "LHPM-2",
        "LHPM-3",
    ]
    assert result["rollover_count"]["evidence"]["sprint_state"] == "closed"


def test_missing_status_produces_confirmed_minimum_counts_and_sorted_evidence(
    db_session: Session,
) -> None:
    db_session.add(_sprint("closed"))
    _add_scope(
        db_session,
        _issue("LHPM-3", None),
        _issue("LHPM-1", "In Progress"),
        _issue("LHPM-4", "  "),
        _issue("LHPM-2", "To Do"),
    )

    result = MetricAvailabilityService.evaluate_sprint_work_state_metrics(
        db_session,
        "10",
        _field_mapper(),
    )

    for metric_name, expected_value in (
        ("in_progress_count", 1),
        ("not_started_count", 1),
        ("rollover_count", 2),
    ):
        assert result[metric_name]["value"] == expected_value
        assert result[metric_name]["status"] == "PARTIAL"
        assert result[metric_name]["available"] is True
        assert result[metric_name]["missing_issue_keys"] == ["LHPM-3", "LHPM-4"]
        assert "confirmed minimum" in result[metric_name]["explanations"][0]


def test_empty_closed_sprint_has_no_computable_unfinished_scope(
    db_session: Session,
) -> None:
    db_session.add(_sprint("closed"))
    db_session.flush()

    result = MetricAvailabilityService.evaluate_sprint_work_state_metrics(
        db_session,
        "10",
        _field_mapper(),
    )

    assert result["rollover_count"]["value"] is None
    assert result["rollover_count"]["status"] == "NOT_COMPUTED"
    assert result["rollover_count"]["available"] is False
    assert result["rollover_count"]["evidence"]["applicable"] is True


def test_not_applicable_metric_does_not_make_overall_response_partial() -> None:
    availability = MetricAvailability(
        context=MetricAvailabilityContext(
            has_tickets=True,
            has_story_points=True,
            has_completed_tickets=True,
            has_release_scope=False,
            has_sprint_scope=True,
            has_changelog=True,
        ),
        metrics={
            "in_progress_count": MetricAvailabilityItem(
                status="COMPUTED",
                available=True,
                reason=None,
                explanations=[],
                missing_issue_keys=[],
                depends_on=["ticket_count", "ticket_status", "sprint_assignment"],
            ),
            "rollover_count": MetricAvailabilityItem(
                status="NOT_APPLICABLE",
                available=False,
                reason="Unfinished closed-sprint scope applies only to closed sprints.",
                explanations=[
                    "Unfinished closed-sprint scope applies only to closed sprints."
                ],
                missing_issue_keys=[],
                depends_on=["ticket_count", "ticket_status", "sprint_assignment"],
            ),
        },
    )

    status, reason = MetricAvailabilityService.computation_state(
        availability,
        is_computed=True,
        empty_scope_reason="No tickets are available for this scope.",
    )

    assert status == "COMPUTED"
    assert reason is None
