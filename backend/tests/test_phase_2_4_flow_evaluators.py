"""Focused contract tests for the Phase 2.4 flow metric evaluators."""

from collections.abc import Generator
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.config import Settings
from app.db.base import Base
from app.models import Issue, IssueHistory, IssueSprint, Release, Sprint
from app.services.analytics_service import AnalyticsService
from app.services.jira_field_mapper import JiraFieldMapper


@pytest.fixture
def db_session() -> Generator[Session, None, None]:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    testing_session = sessionmaker(bind=engine, autoflush=False, class_=Session)
    with testing_session() as session:
        yield session


@pytest.fixture
def field_mapper() -> JiraFieldMapper:
    return JiraFieldMapper(Settings())


def _release() -> Release:
    return Release(
        release_id="R1",
        name="v1.0",
        project_key="PROJ",
        status="unreleased",
    )


def _sprint() -> Sprint:
    return Sprint(
        sprint_id="10",
        name="Sprint 10",
        state="active",
        project_key="PROJ",
        board_id="1",
    )


def _issue(
    issue_key: str,
    status: str | None,
    *,
    release_id: str | None = "R1",
    history_complete: bool = True,
) -> Issue:
    return Issue(
        issue_key=issue_key,
        summary=issue_key,
        issue_type="Story",
        status=status,
        priority="Medium",
        release_id=release_id,
        jira_changelog_complete=history_complete,
    )


def _history(
    issue_key: str,
    old_value: str | None,
    new_value: str | None,
    changed_at: datetime,
    *,
    field_name: str = "status",
) -> IssueHistory:
    return IssueHistory(
        issue_key=issue_key,
        field_name=field_name,
        old_value=old_value,
        new_value=new_value,
        changed_at=changed_at,
    )


def test_cycle_time_uses_first_done_strictly_after_start(
    db_session: Session,
    field_mapper: JiraFieldMapper,
) -> None:
    base = datetime(2026, 7, 1, tzinfo=UTC)
    db_session.add(_release())
    db_session.add(_issue("PROJ-1", " Done "))
    db_session.flush()
    db_session.add_all(
        [
            _history("PROJ-1", "In Progress", "Done", base - timedelta(days=1)),
            _history("PROJ-1", "To Do", "IN PROGRESS", base),
            _history("PROJ-1", "In Progress", "DONE", base + timedelta(days=2)),
            _history("PROJ-1", "Done", "Closed", base + timedelta(days=3)),
        ]
    )
    db_session.flush()

    result = AnalyticsService.evaluate_release_flow_metrics(db_session, "R1", field_mapper)
    cycle = result["median_cycle_time_days"]

    assert cycle["status"] == "COMPUTED"
    assert cycle["median_cycle_time_days"] == 2.0
    assert cycle["evidence"]["included_issues"] == [
        {
            "issue_key": "PROJ-1",
            "start_at": base.isoformat(),
            "end_at": (base + timedelta(days=2)).isoformat(),
            "duration_days": 2.0,
        }
    ]


def test_cycle_time_returns_median_rounded_to_four_decimals(
    db_session: Session,
    field_mapper: JiraFieldMapper,
) -> None:
    base = datetime(2026, 7, 1, tzinfo=UTC)
    db_session.add(_release())
    db_session.add_all([_issue("PROJ-1", "Done"), _issue("PROJ-2", "Done")])
    db_session.flush()
    db_session.add_all(
        [
            _history("PROJ-1", "To Do", "In Progress", base),
            _history("PROJ-1", "In Progress", "Done", base + timedelta(seconds=100_001)),
            _history("PROJ-2", "To Do", "In Progress", base),
            _history("PROJ-2", "In Progress", "Done", base + timedelta(seconds=200_002)),
        ]
    )
    db_session.flush()

    cycle = AnalyticsService.evaluate_release_flow_metrics(
        db_session, "R1", field_mapper
    )["median_cycle_time_days"]

    assert cycle["status"] == "COMPUTED"
    assert cycle["median_cycle_time_days"] == 1.7361


def test_cycle_time_partial_retains_confirmed_evidence_and_sorted_missing_keys(
    db_session: Session,
    field_mapper: JiraFieldMapper,
) -> None:
    base = datetime(2026, 7, 1, tzinfo=UTC)
    db_session.add(_release())
    db_session.add_all(
        [
            _issue("PROJ-3", "Done", history_complete=False),
            _issue("PROJ-2", None),
            _issue("PROJ-1", "Done"),
        ]
    )
    db_session.flush()
    db_session.add_all(
        [
            _history("PROJ-1", "To Do", "In Progress", base),
            _history("PROJ-1", "In Progress", "Done", base + timedelta(days=1)),
        ]
    )
    db_session.flush()

    cycle = AnalyticsService.evaluate_release_flow_metrics(
        db_session, "R1", field_mapper
    )["median_cycle_time_days"]

    assert cycle["status"] == "PARTIAL"
    assert cycle["median_cycle_time_days"] is None
    assert cycle["missing_issue_keys"] == ["PROJ-2", "PROJ-3"]
    assert [item["issue_key"] for item in cycle["evidence"]["included_issues"]] == ["PROJ-1"]


def test_cycle_time_not_computed_groups_complete_ticket_without_valid_pair(
    db_session: Session,
    field_mapper: JiraFieldMapper,
) -> None:
    base = datetime(2026, 7, 1, tzinfo=UTC)
    db_session.add(_release())
    db_session.add(_issue("PROJ-1", "Done"))
    db_session.flush()
    db_session.add(_history("PROJ-1", "To Do", "Done", base))
    db_session.flush()

    cycle = AnalyticsService.evaluate_release_flow_metrics(
        db_session, "R1", field_mapper
    )["median_cycle_time_days"]

    assert cycle["status"] == "NOT_COMPUTED"
    assert cycle["median_cycle_time_days"] is None
    assert cycle["evidence"]["no_in_progress_issue_keys"] == ["PROJ-1"]


def test_reopen_rate_counts_each_distinct_event_and_can_exceed_one_hundred(
    db_session: Session,
    field_mapper: JiraFieldMapper,
) -> None:
    base = datetime(2026, 7, 1, tzinfo=UTC)
    db_session.add(_release())
    db_session.add_all(
        [
            _issue("PROJ-1", "In Review"),
            _issue("PROJ-2", "To Do"),
        ]
    )
    db_session.flush()
    third_reopen = _history(
        "PROJ-1",
        "Closed",
        "In Review",
        base + timedelta(hours=5),
        field_name=" STATUS ",
    )
    db_session.add_all(
        [
            _history("PROJ-1", "To Do", "Done", base),
            _history("PROJ-1", "Done", "In Progress", base + timedelta(hours=1)),
            _history("PROJ-1", "In Progress", "Resolved", base + timedelta(hours=2)),
            _history("PROJ-1", "Resolved", "To Do", base + timedelta(hours=3)),
            _history("PROJ-1", "To Do", "Closed", base + timedelta(hours=4)),
            third_reopen,
            _history(
                "PROJ-1",
                "Closed",
                "In Review",
                base + timedelta(hours=5),
                field_name="status",
            ),
        ]
    )
    db_session.flush()

    reopen = AnalyticsService.evaluate_release_flow_metrics(
        db_session, "R1", field_mapper
    )["reopen_rate_pct"]

    assert reopen["status"] == "COMPUTED"
    assert reopen["reopen_rate_pct"] == 300.0
    assert reopen["confirmed_eligible_ticket_count"] == 1
    assert reopen["confirmed_reopen_event_count"] == 3
    assert reopen["evidence"]["event_count_by_issue"] == {"PROJ-1": 3}
    assert reopen["explanations"] == [
        "Ticket PROJ-1 was counted 3 times because it was reopened 3 times."
    ]


def test_reopen_rate_partial_returns_confirmed_counts_but_null_percentage(
    db_session: Session,
    field_mapper: JiraFieldMapper,
) -> None:
    base = datetime(2026, 7, 1, tzinfo=UTC)
    db_session.add(_release())
    db_session.add_all(
        [
            _issue("PROJ-1", "Done", history_complete=False),
            _issue("PROJ-2", None),
        ]
    )
    db_session.flush()
    db_session.add_all(
        [
            _history("PROJ-1", "To Do", "Done", base),
            _history("PROJ-1", "Done", "In Progress", base + timedelta(hours=1)),
        ]
    )
    db_session.flush()

    reopen = AnalyticsService.evaluate_release_flow_metrics(
        db_session, "R1", field_mapper
    )["reopen_rate_pct"]

    assert reopen["status"] == "PARTIAL"
    assert reopen["reopen_rate_pct"] is None
    assert reopen["confirmed_eligible_ticket_count"] == 1
    assert reopen["confirmed_reopen_event_count"] == 1
    assert reopen["missing_issue_keys"] == ["PROJ-1", "PROJ-2"]


def test_reopen_rate_not_computed_when_no_ticket_reached_done(
    db_session: Session,
    field_mapper: JiraFieldMapper,
) -> None:
    db_session.add(_release())
    db_session.add(_issue("PROJ-1", "To Do"))
    db_session.flush()

    reopen = AnalyticsService.evaluate_release_flow_metrics(
        db_session, "R1", field_mapper
    )["reopen_rate_pct"]

    assert reopen["status"] == "NOT_COMPUTED"
    assert reopen["reopen_rate_pct"] is None
    assert reopen["confirmed_eligible_ticket_count"] == 0
    assert reopen["confirmed_reopen_event_count"] == 0


def test_release_and_sprint_membership_use_the_same_flow_contract(
    db_session: Session,
    field_mapper: JiraFieldMapper,
) -> None:
    base = datetime(2026, 7, 1, tzinfo=UTC)
    db_session.add_all([_release(), _sprint(), _issue("PROJ-1", "Done")])
    db_session.add(IssueSprint(issue_key="PROJ-1", sprint_id="10"))
    db_session.flush()
    db_session.add_all(
        [
            _history("PROJ-1", "To Do", "In Progress", base),
            _history("PROJ-1", "In Progress", "Done", base + timedelta(days=2)),
        ]
    )
    db_session.flush()

    release_result = AnalyticsService.evaluate_release_flow_metrics(db_session, "R1", field_mapper)
    sprint_result = AnalyticsService.evaluate_sprint_flow_metrics(db_session, "10", field_mapper)

    assert sprint_result == release_result
