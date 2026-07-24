from collections.abc import Generator
from datetime import UTC, datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.config import Settings
from app.db.base import Base
from app.models import Issue, IssueSprint, Sprint
from app.services.jira_field_mapper import JiraFieldMapper
from app.services.metric_availability_service import MetricAvailabilityService


@pytest.fixture
def db_session() -> Generator[Session, None, None]:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    testing_session_local = sessionmaker(
        bind=engine,
        autoflush=False,
        autocommit=False,
        class_=Session,
    )
    Base.metadata.create_all(bind=engine)
    with testing_session_local() as session:
        yield session


def _field_mapper(done_statuses: str = "done,closed,resolved") -> JiraFieldMapper:
    return JiraFieldMapper(Settings(_env_file=None, jira_done_statuses=done_statuses))


def _sprint() -> Sprint:
    return Sprint(
        sprint_id="10",
        name="Sprint 10",
        state="active",
        project_key="LHPM",
        board_id="1",
        start_date=None,
        end_date=None,
        complete_date=None,
        goal=None,
    )


def _issue(issue_key: str, status: str | None) -> Issue:
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
        jira_created_at=datetime.now(UTC),
        jira_changelog_complete=True,
        created_at=datetime.now(UTC),
    )


def _add_scope(db_session: Session, *issues: Issue) -> None:
    db_session.add_all(issues)
    db_session.add_all(
        IssueSprint(issue_key=issue.issue_key, sprint_id="10") for issue in reversed(issues)
    )
    db_session.flush()


def test_empty_sprint_scope_is_not_computed(db_session: Session) -> None:
    db_session.add(_sprint())
    db_session.flush()

    result = MetricAvailabilityService.evaluate_sprint_scope_metrics(
        db_session,
        "10",
        _field_mapper(),
    )

    assert result["committed_scope"] == {
        "value": None,
        "status": "NOT_COMPUTED",
        "available": False,
        "explanations": ["No tickets are available for this scope."],
        "missing_issue_keys": [],
        "evidence": {"current_scope_issue_keys": [], "current_scope_count": 0},
    }
    assert result["completed_scope_pct"]["value"] is None
    assert result["completed_scope_pct"]["status"] == "NOT_COMPUTED"
    assert result["completed_scope_pct"]["available"] is False


def test_sprint_scope_uses_sorted_current_membership_and_ticket_statuses(
    db_session: Session,
) -> None:
    db_session.add(_sprint())
    _add_scope(
        db_session,
        _issue("LHPM-3", "To Do"),
        _issue("LHPM-1", "Done"),
        _issue("LHPM-2", "Closed"),
    )

    result = MetricAvailabilityService.evaluate_sprint_scope_metrics(
        db_session,
        "10",
        _field_mapper(),
    )

    assert result["committed_scope"]["value"] == 3
    assert result["committed_scope"]["status"] == "COMPUTED"
    assert result["committed_scope"]["evidence"] == {
        "current_scope_issue_keys": ["LHPM-1", "LHPM-2", "LHPM-3"],
        "current_scope_count": 3,
    }
    assert result["completed_scope_pct"]["value"] == 66.67
    assert result["completed_scope_pct"]["status"] == "COMPUTED"
    assert result["completed_scope_pct"]["evidence"]["completed_issue_keys"] == [
        "LHPM-1",
        "LHPM-2",
    ]


def test_missing_status_keeps_scope_count_but_makes_completion_partial(
    db_session: Session,
) -> None:
    db_session.add(_sprint())
    _add_scope(
        db_session,
        _issue("LHPM-2", None),
        _issue("LHPM-1", "Done"),
    )

    result = MetricAvailabilityService.evaluate_sprint_scope_metrics(
        db_session,
        "10",
        _field_mapper(),
    )

    assert result["committed_scope"]["value"] == 2
    assert result["committed_scope"]["status"] == "COMPUTED"
    assert result["completed_scope_pct"]["value"] is None
    assert result["completed_scope_pct"]["status"] == "PARTIAL"
    assert result["completed_scope_pct"]["available"] is False
    assert result["completed_scope_pct"]["missing_issue_keys"] == ["LHPM-2"]
    assert result["completed_scope_pct"]["evidence"]["current_scope_issue_keys"] == [
        "LHPM-1",
        "LHPM-2",
    ]


def test_completed_scope_uses_configured_done_statuses(db_session: Session) -> None:
    db_session.add(_sprint())
    _add_scope(
        db_session,
        _issue("LHPM-2", "Done"),
        _issue("LHPM-1", " SHIPPED "),
    )

    result = MetricAvailabilityService.evaluate_sprint_scope_metrics(
        db_session,
        "10",
        _field_mapper("shipped"),
    )

    assert result["completed_scope_pct"]["value"] == 50.0
    assert result["completed_scope_pct"]["evidence"]["completed_issue_keys"] == [
        "LHPM-1"
    ]
