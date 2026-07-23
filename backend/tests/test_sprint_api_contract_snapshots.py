from __future__ import annotations

from collections.abc import Generator
from datetime import UTC, datetime, timedelta
from pathlib import Path

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

import app.api.sprints as sprints_api
import app.main as main_module
import app.repositories.operational_status_repository as operational_status_repository
import app.services.analytics_service as analytics_service
from app.config import get_settings
from app.db.base import Base
from app.db.session import get_db_session
from app.main import app
from app.models import Issue, IssueHistory, IssueSprint, Sprint
from app.services.analytics_service import AnalyticsService
from tests.api_contract_snapshots import assert_api_contract_snapshot


FIRST_SNAPSHOT_AT = datetime(2026, 7, 20, 12, tzinfo=UTC)
SECOND_SNAPSHOT_AT = datetime(2026, 7, 21, 13, tzinfo=UTC)
RESPONSE_AT = datetime(2026, 7, 21, 19, tzinfo=UTC)


class FrozenDateTimeMeta(type):
    def __instancecheck__(cls, instance: object) -> bool:
        return isinstance(instance, datetime)


class FrozenDateTime(datetime, metaclass=FrozenDateTimeMeta):
    current = FIRST_SNAPSHOT_AT

    @classmethod
    def now(cls, tz=None):
        value = cls.current
        if tz is None:
            return value.replace(tzinfo=None)
        return value.astimezone(tz)


@pytest.fixture
def sprint_contract_client(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> Generator[TestClient, None, None]:
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

    def override_get_db_session() -> Generator[Session, None, None]:
        session = testing_session_local()
        try:
            yield session
        finally:
            session.close()

    monkeypatch.setenv("LIGHTHOUSE_CONFIG_FILE", str(tmp_path / "absent.env"))
    monkeypatch.setenv("JIRA_FIELD_SEVERITY", "priority")
    monkeypatch.setenv("JIRA_DONE_STATUSES", "done,closed,resolved")
    monkeypatch.setenv(
        "JIRA_IN_PROGRESS_STATUSES",
        "in progress,in development,in review,in testing",
    )
    monkeypatch.setenv("JIRA_HIGH_SEVERITY_VALUES", "high,highest,critical")
    monkeypatch.setenv("JIRA_BUG_ISSUE_TYPES", "bug")
    monkeypatch.setenv("JIRA_BLOCKER_ISSUE_TYPES", "blocker,incident")
    monkeypatch.setenv(
        "JIRA_BLOCKER_SEVERITY_VALUES",
        "blocker,highest,critical",
    )
    monkeypatch.setenv("JIRA_BLOCKED_STATUSES", "blocked")
    monkeypatch.setenv("JIRA_CHANGELOG_FIX_VERSION_FIELDS", "fix version,fixversion")
    monkeypatch.setenv("JIRA_CHANGELOG_SPRINT_FIELDS", "sprint")
    get_settings.cache_clear()

    monkeypatch.setattr(analytics_service, "datetime", FrozenDateTime)
    monkeypatch.setattr(operational_status_repository, "datetime", FrozenDateTime)
    monkeypatch.setattr(sprints_api, "datetime", FrozenDateTime)
    monkeypatch.setattr(main_module, "init_db", lambda: None)
    app.dependency_overrides[get_db_session] = override_get_db_session
    app.state.testing_session_local = testing_session_local

    with testing_session_local() as session:
        _seed_sprint_contract_data(session)

    FrozenDateTime.current = RESPONSE_AT
    try:
        with TestClient(app) as client:
            yield client
    finally:
        del app.state.testing_session_local
        app.dependency_overrides.clear()
        get_settings.cache_clear()


def _seed_sprint(
    session: Session,
    *,
    sprint_id: str,
    name: str,
    state: str,
    project_key: str,
    start_date: datetime,
    end_date: datetime,
    complete_date: datetime | None,
    goal: str | None,
    created_at: datetime,
    updated_at: datetime,
) -> None:
    session.add(
        Sprint(
            sprint_id=sprint_id,
            name=name,
            state=state,
            project_key=project_key,
            board_id="board-7",
            start_date=start_date,
            end_date=end_date,
            complete_date=complete_date,
            goal=goal,
            created_at=created_at,
            updated_at=updated_at,
        )
    )


def _seed_issue(
    session: Session,
    *,
    sprint_id: str,
    issue_key: str,
    status: str,
    story_points: float | None,
    created_at: datetime,
    assignee: str,
    assignee_id: str,
) -> None:
    session.add(
        Issue(
            issue_key=issue_key,
            summary=f"Contract fixture {issue_key}",
            issue_type="Story",
            status=status,
            priority="Medium",
            assignee=assignee,
            jira_assignee_id=assignee_id,
            story_points=story_points,
            release_id=None,
            is_blocker=False,
            jira_blocker_flag=False,
            jira_changelog_complete=True,
            jira_created_at=created_at,
            jira_updated_at=created_at,
            created_at=created_at,
            updated_at=created_at,
        )
    )
    session.add(
        IssueSprint(
            issue_key=issue_key,
            sprint_id=sprint_id,
            created_at=created_at,
        )
    )


def _seed_history(
    session: Session,
    issue_key: str,
    old_value: str,
    new_value: str,
    changed_at: datetime,
) -> None:
    session.add(
        IssueHistory(
            issue_key=issue_key,
            field_name="status",
            old_value=old_value,
            new_value=new_value,
            changed_at=changed_at,
        )
    )


def _recompute_sprint(
    session: Session,
    sprint_id: str,
    snapshot_at: datetime,
):
    FrozenDateTime.current = snapshot_at
    snapshot = AnalyticsService().recompute_sprint_metrics(session, sprint_id)
    session.commit()
    return snapshot


def _seed_sprint_contract_data(session: Session) -> None:
    created_at = datetime(2026, 5, 20, 8, tzinfo=UTC)
    _seed_sprint(
        session,
        sprint_id="LHPM-SPRINT-39",
        name="Sprint 39 Baseline",
        state="closed",
        project_key="LHPM",
        start_date=datetime(2026, 6, 16, tzinfo=UTC),
        end_date=datetime(2026, 6, 29, tzinfo=UTC),
        complete_date=datetime(2026, 6, 29, 18, tzinfo=UTC),
        goal="Establish a complete historical velocity baseline.",
        created_at=created_at,
        updated_at=datetime(2026, 6, 29, 18, tzinfo=UTC),
    )
    _seed_sprint(
        session,
        sprint_id="LHPM-SPRINT-40",
        name="Sprint 40 Inconclusive",
        state="future",
        project_key="LHPM",
        start_date=datetime(2026, 7, 22, tzinfo=UTC),
        end_date=datetime(2026, 8, 3, tzinfo=UTC),
        complete_date=None,
        goal=None,
        created_at=created_at + timedelta(hours=1),
        updated_at=datetime(2026, 7, 10, 9, tzinfo=UTC),
    )
    _seed_sprint(
        session,
        sprint_id="LHPM-SPRINT-41",
        name="Sprint 41 Partial",
        state="future",
        project_key="LHPM",
        start_date=datetime(2026, 7, 22, tzinfo=UTC),
        end_date=datetime(2026, 8, 5, tzinfo=UTC),
        complete_date=None,
        goal="Show partial story-point coverage honestly.",
        created_at=created_at + timedelta(hours=2),
        updated_at=datetime(2026, 7, 10, 10, tzinfo=UTC),
    )
    _seed_sprint(
        session,
        sprint_id="LHPM-SPRINT-42",
        name="Sprint 42 Complete",
        state="active",
        project_key="LHPM",
        start_date=datetime(2026, 7, 14, tzinfo=UTC),
        end_date=datetime(2026, 7, 28, tzinfo=UTC),
        complete_date=None,
        goal="Protect complete delivery and reopen evidence.",
        created_at=created_at + timedelta(hours=3),
        updated_at=datetime(2026, 7, 14, 8, tzinfo=UTC),
    )
    _seed_sprint(
        session,
        sprint_id="OTHER-SPRINT-99",
        name="Other Project Sprint",
        state="active",
        project_key="OTHER",
        start_date=datetime(2026, 7, 15, tzinfo=UTC),
        end_date=datetime(2026, 7, 29, tzinfo=UTC),
        complete_date=None,
        goal="Excluded by project-scoped sprint requests.",
        created_at=created_at + timedelta(hours=4),
        updated_at=datetime(2026, 7, 15, 8, tzinfo=UTC),
    )

    _seed_issue(
        session,
        sprint_id="LHPM-SPRINT-39",
        issue_key="LHPM-3901",
        status="Done",
        story_points=5.0,
        created_at=datetime(2026, 6, 16, 9, tzinfo=UTC),
        assignee="Ada",
        assignee_id="account-ada",
    )
    _seed_issue(
        session,
        sprint_id="LHPM-SPRINT-39",
        issue_key="LHPM-3902",
        status="Done",
        story_points=3.0,
        created_at=datetime(2026, 6, 16, 10, tzinfo=UTC),
        assignee="Grace",
        assignee_id="account-grace",
    )
    _seed_history(
        session,
        "LHPM-3901",
        "To Do",
        "In Progress",
        datetime(2026, 6, 17, 9, tzinfo=UTC),
    )
    _seed_history(
        session,
        "LHPM-3901",
        "In Progress",
        "Done",
        datetime(2026, 6, 20, 9, tzinfo=UTC),
    )
    _seed_history(
        session,
        "LHPM-3902",
        "To Do",
        "In Progress",
        datetime(2026, 6, 17, 10, tzinfo=UTC),
    )
    _seed_history(
        session,
        "LHPM-3902",
        "In Progress",
        "Done",
        datetime(2026, 6, 21, 10, tzinfo=UTC),
    )

    _seed_issue(
        session,
        sprint_id="LHPM-SPRINT-40",
        issue_key="LHPM-4001",
        status="Done",
        story_points=3.0,
        created_at=datetime(2026, 7, 16, 9, tzinfo=UTC),
        assignee="Ada",
        assignee_id="account-ada",
    )
    _seed_issue(
        session,
        sprint_id="LHPM-SPRINT-40",
        issue_key="LHPM-4002",
        status="To Do",
        story_points=None,
        created_at=datetime(2026, 7, 16, 10, tzinfo=UTC),
        assignee="Grace",
        assignee_id="account-grace",
    )
    _seed_issue(
        session,
        sprint_id="LHPM-SPRINT-40",
        issue_key="LHPM-4003",
        status="In Progress",
        story_points=None,
        created_at=datetime(2026, 7, 16, 11, tzinfo=UTC),
        assignee="Linus",
        assignee_id="account-linus",
    )
    _seed_history(
        session,
        "LHPM-4001",
        "To Do",
        "In Progress",
        datetime(2026, 7, 17, 9, tzinfo=UTC),
    )
    _seed_history(
        session,
        "LHPM-4001",
        "In Progress",
        "Done",
        datetime(2026, 7, 19, 9, tzinfo=UTC),
    )

    _seed_issue(
        session,
        sprint_id="LHPM-SPRINT-41",
        issue_key="LHPM-4101",
        status="Done",
        story_points=5.0,
        created_at=datetime(2026, 7, 16, 12, tzinfo=UTC),
        assignee="Ada",
        assignee_id="account-ada",
    )
    _seed_issue(
        session,
        sprint_id="LHPM-SPRINT-41",
        issue_key="LHPM-4102",
        status="To Do",
        story_points=None,
        created_at=datetime(2026, 7, 16, 13, tzinfo=UTC),
        assignee="Grace",
        assignee_id="account-grace",
    )
    _seed_history(
        session,
        "LHPM-4101",
        "To Do",
        "In Progress",
        datetime(2026, 7, 17, 12, tzinfo=UTC),
    )
    _seed_history(
        session,
        "LHPM-4101",
        "In Progress",
        "Done",
        datetime(2026, 7, 19, 12, tzinfo=UTC),
    )

    _seed_issue(
        session,
        sprint_id="LHPM-SPRINT-42",
        issue_key="LHPM-4201",
        status="In Progress",
        story_points=5.0,
        created_at=datetime(2026, 7, 14, 9, tzinfo=UTC),
        assignee="Ada",
        assignee_id="account-ada",
    )
    _seed_issue(
        session,
        sprint_id="LHPM-SPRINT-42",
        issue_key="LHPM-4202",
        status="In Progress",
        story_points=3.0,
        created_at=datetime(2026, 7, 14, 10, tzinfo=UTC),
        assignee="Grace",
        assignee_id="account-grace",
    )
    _seed_issue(
        session,
        sprint_id="LHPM-SPRINT-42",
        issue_key="LHPM-4203",
        status="Done",
        story_points=2.0,
        created_at=datetime(2026, 7, 14, 11, tzinfo=UTC),
        assignee="Linus",
        assignee_id="account-linus",
    )
    repeated_transitions = [
        ("To Do", "Done", datetime(2026, 7, 14, 12, tzinfo=UTC)),
        ("Done", "In Progress", datetime(2026, 7, 15, 9, tzinfo=UTC)),
        ("In Progress", "Resolved", datetime(2026, 7, 16, 9, tzinfo=UTC)),
        ("Resolved", "To Do", datetime(2026, 7, 17, 9, tzinfo=UTC)),
        ("To Do", "Closed", datetime(2026, 7, 18, 9, tzinfo=UTC)),
        ("Closed", "In Review", datetime(2026, 7, 19, 9, tzinfo=UTC)),
        ("In Review", "Done", datetime(2026, 7, 19, 15, tzinfo=UTC)),
        ("Done", "In Progress", datetime(2026, 7, 19, 18, tzinfo=UTC)),
    ]
    for old_value, new_value, changed_at in repeated_transitions:
        _seed_history(
            session,
            "LHPM-4201",
            old_value,
            new_value,
            changed_at,
        )
    _seed_history(
        session,
        "LHPM-4202",
        "To Do",
        "In Progress",
        datetime(2026, 7, 15, 10, tzinfo=UTC),
    )
    _seed_history(
        session,
        "LHPM-4203",
        "To Do",
        "In Progress",
        datetime(2026, 7, 15, 11, tzinfo=UTC),
    )
    _seed_history(
        session,
        "LHPM-4203",
        "In Progress",
        "Done",
        datetime(2026, 7, 17, 11, tzinfo=UTC),
    )
    session.commit()

    _recompute_sprint(session, "LHPM-SPRINT-42", FIRST_SNAPSHOT_AT)
    completed_issue = session.scalar(
        select(Issue).where(Issue.issue_key == "LHPM-4202")
    )
    assert completed_issue is not None
    completed_issue.status = "Done"
    completed_issue.jira_updated_at = SECOND_SNAPSHOT_AT - timedelta(hours=1)
    completed_issue.updated_at = SECOND_SNAPSHOT_AT - timedelta(hours=1)
    _seed_history(
        session,
        "LHPM-4202",
        "In Progress",
        "Done",
        SECOND_SNAPSHOT_AT - timedelta(hours=1),
    )
    session.commit()
    complete_snapshot = _recompute_sprint(
        session,
        "LHPM-SPRINT-42",
        SECOND_SNAPSHOT_AT,
    )
    reopen_evidence = complete_snapshot.calculation_provenance["metric_evidence"][
        "reopen_rate_pct"
    ]
    assert reopen_evidence["event_count_by_issue"] == {"LHPM-4201": 4}
    assert reopen_evidence["repeated_event_explanations"] == [
        "Ticket LHPM-4201 was counted 4 times because it was reopened 4 times."
    ]
    assert complete_snapshot.story_point_coverage_pct == 100.0

    partial_snapshot = _recompute_sprint(
        session,
        "LHPM-SPRINT-41",
        SECOND_SNAPSHOT_AT,
    )
    assert partial_snapshot.story_point_coverage_pct == 50.0
    assert partial_snapshot.delivery_confidence_status == "PARTIAL"
    assert partial_snapshot.delivery_confidence_score is not None

    inconclusive_snapshot = _recompute_sprint(
        session,
        "LHPM-SPRINT-40",
        SECOND_SNAPSHOT_AT,
    )
    assert inconclusive_snapshot.story_point_coverage_pct == 33.33
    assert inconclusive_snapshot.delivery_confidence_status == "INCONCLUSIVE"
    assert inconclusive_snapshot.delivery_confidence_score is None


@pytest.mark.parametrize(
    ("contract_id", "path"),
    [
        (
            "sprint.collection.project-scoped.200",
            "/sprints?state=future&project_key=LHPM&skip=0&limit=1",
        ),
        (
            "sprint.current.project-scoped.200",
            "/sprints/current?project_key=LHPM",
        ),
        (
            "sprint.metrics.complete-reopen-evidence.200",
            "/sprints/LHPM-SPRINT-42/metrics",
        ),
        (
            "sprint.metrics.partial-coverage.200",
            "/sprints/LHPM-SPRINT-41/metrics",
        ),
        (
            "sprint.metrics.inconclusive-coverage.200",
            "/sprints/LHPM-SPRINT-40/metrics",
        ),
        (
            "sprint.snapshot-comparison.200",
            "/sprints/LHPM-SPRINT-42/snapshot-comparison?baseline=previous",
        ),
    ],
    ids=[
        "collection",
        "current",
        "metrics_complete",
        "metrics_partial",
        "metrics_inconclusive",
        "comparison",
    ],
)
def test_sprint_payload_matches_contract(
    sprint_contract_client: TestClient,
    contract_id: str,
    path: str,
) -> None:
    response = sprint_contract_client.get(path)

    assert_api_contract_snapshot(
        contract_id,
        status_code=response.status_code,
        payload=response.json(),
    )
