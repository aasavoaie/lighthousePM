from __future__ import annotations

from collections.abc import Generator
from datetime import UTC, datetime, timedelta
from pathlib import Path

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

import app.api.metrics as metrics_api
import app.main as main_module
import app.repositories.operational_status_repository as operational_status_repository
import app.services.analytics_service as analytics_service
import app.services.signal_service as signal_service
from app.config import get_settings
from app.db.base import Base
from app.db.session import get_db_session
from app.main import app
from app.models import Issue, IssueHistory, Release
from app.services.analytics_service import AnalyticsService
from app.services.signal_service import SignalService
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
def release_contract_client(
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
    monkeypatch.setattr(signal_service, "datetime", FrozenDateTime)
    monkeypatch.setattr(operational_status_repository, "datetime", FrozenDateTime)
    monkeypatch.setattr(metrics_api, "datetime", FrozenDateTime)
    monkeypatch.setattr(main_module, "init_db", lambda: None)
    app.dependency_overrides[get_db_session] = override_get_db_session
    app.state.testing_session_local = testing_session_local

    with testing_session_local() as session:
        _seed_release_contract_data(session)

    FrozenDateTime.current = RESPONSE_AT
    try:
        with TestClient(app) as client:
            yield client
    finally:
        del app.state.testing_session_local
        app.dependency_overrides.clear()
        get_settings.cache_clear()


def _seed_release(
    session: Session,
    *,
    release_id: str,
    name: str,
    project_key: str,
    description: str | None,
    status: str | None,
    start_date: datetime | None,
    release_date: datetime | None,
    created_at: datetime,
    updated_at: datetime,
) -> None:
    session.add(
        Release(
            release_id=release_id,
            name=name,
            project_key=project_key,
            description=description,
            status=status,
            start_date=start_date,
            release_date=release_date,
            created_at=created_at,
            updated_at=updated_at,
        )
    )


def _seed_issue(
    session: Session,
    *,
    issue_key: str,
    release_id: str,
    status: str | None,
    issue_type: str | None = "Story",
    priority: str | None = "Medium",
    story_points: float | None = None,
    blocker_flag: bool | None = None,
    changelog_complete: bool = True,
    created_at: datetime,
) -> None:
    session.add(
        Issue(
            issue_key=issue_key,
            summary=f"Contract fixture {issue_key}",
            issue_type=issue_type,
            status=status,
            priority=priority,
            assignee="Ada",
            jira_assignee_id="account-ada",
            story_points=story_points,
            release_id=release_id,
            is_blocker=blocker_flag is True,
            jira_blocker_flag=blocker_flag,
            jira_changelog_complete=changelog_complete,
            jira_created_at=created_at,
            jira_updated_at=created_at,
            created_at=created_at,
            updated_at=created_at,
        )
    )


def _seed_history(
    session: Session,
    issue_key: str,
    field_name: str,
    old_value: str | None,
    new_value: str | None,
    changed_at: datetime,
) -> None:
    session.add(
        IssueHistory(
            issue_key=issue_key,
            field_name=field_name,
            old_value=old_value,
            new_value=new_value,
            changed_at=changed_at,
        )
    )


def _recompute_release(
    session: Session, release_id: str, snapshot_at: datetime
) -> None:
    FrozenDateTime.current = snapshot_at
    AnalyticsService().recompute_release_metrics(session, release_id)
    stored_signal = SignalService().recompute_release_signal(session, release_id)
    stored_signal.created_at = snapshot_at
    stored_signal.updated_at = snapshot_at
    session.commit()


def _seed_release_contract_data(session: Session) -> None:
    created_at = datetime(2026, 7, 1, 8, tzinfo=UTC)
    _seed_release(
        session,
        release_id="LHPM-REL-ALPHA",
        name="Alpha Release",
        project_key="LHPM",
        description="Primary deterministic release contract fixture.",
        status="active",
        start_date=datetime(2026, 7, 1, tzinfo=UTC),
        release_date=datetime(2026, 7, 31, tzinfo=UTC),
        created_at=created_at,
        updated_at=datetime(2026, 7, 18, 9, 30, tzinfo=UTC),
    )
    _seed_release(
        session,
        release_id="LHPM-REL-PARTIAL",
        name="Partial Evidence Release",
        project_key="LHPM",
        description=None,
        status=None,
        start_date=None,
        release_date=None,
        created_at=created_at + timedelta(hours=1),
        updated_at=datetime(2026, 7, 19, 10, tzinfo=UTC),
    )
    _seed_release(
        session,
        release_id="OTHER-REL-1",
        name="Other Project Release",
        project_key="OTHER",
        description="Excluded by the LHPM project filter.",
        status="active",
        start_date=datetime(2026, 7, 2, tzinfo=UTC),
        release_date=datetime(2026, 8, 1, tzinfo=UTC),
        created_at=created_at + timedelta(hours=2),
        updated_at=datetime(2026, 7, 19, 11, tzinfo=UTC),
    )

    _seed_issue(
        session,
        issue_key="LHPM-101",
        release_id="LHPM-REL-ALPHA",
        status="In Progress",
        story_points=5.0,
        blocker_flag=True,
        created_at=datetime(2026, 7, 10, 9, tzinfo=UTC),
    )
    _seed_issue(
        session,
        issue_key="LHPM-102",
        release_id="LHPM-REL-ALPHA",
        status="In Progress",
        story_points=3.0,
        blocker_flag=True,
        created_at=datetime(2026, 7, 11, 10, tzinfo=UTC),
    )
    _seed_issue(
        session,
        issue_key="LHPM-103",
        release_id="LHPM-REL-ALPHA",
        status="Done",
        story_points=2.0,
        created_at=datetime(2026, 7, 12, 11, tzinfo=UTC),
    )
    _seed_history(
        session,
        "LHPM-101",
        "status",
        "To Do",
        "In Progress",
        datetime(2026, 7, 16, 9, tzinfo=UTC),
    )
    _seed_history(
        session,
        "LHPM-102",
        "status",
        "To Do",
        "In Progress",
        datetime(2026, 7, 16, 10, tzinfo=UTC),
    )
    _seed_history(
        session,
        "LHPM-103",
        "status",
        "To Do",
        "In Progress",
        datetime(2026, 7, 16, 11, tzinfo=UTC),
    )
    _seed_history(
        session,
        "LHPM-103",
        "status",
        "In Progress",
        "Done",
        datetime(2026, 7, 18, 11, tzinfo=UTC),
    )
    _seed_history(
        session,
        "LHPM-103",
        "fix version",
        None,
        "Alpha Release",
        datetime(2026, 7, 19, 12, tzinfo=UTC),
    )
    session.commit()

    _recompute_release(session, "LHPM-REL-ALPHA", FIRST_SNAPSHOT_AT)

    resolved_issue = session.scalar(select(Issue).where(Issue.issue_key == "LHPM-102"))
    assert resolved_issue is not None
    resolved_issue.status = "Done"
    resolved_issue.jira_updated_at = SECOND_SNAPSHOT_AT - timedelta(hours=1)
    resolved_issue.updated_at = SECOND_SNAPSHOT_AT - timedelta(hours=1)
    _seed_history(
        session,
        "LHPM-102",
        "status",
        "In Progress",
        "Done",
        SECOND_SNAPSHOT_AT - timedelta(hours=1),
    )
    session.commit()
    _recompute_release(session, "LHPM-REL-ALPHA", SECOND_SNAPSHOT_AT)

    partial_created_at = datetime(2026, 7, 13, 8, tzinfo=UTC)
    _seed_issue(
        session,
        issue_key="LHPM-201",
        release_id="LHPM-REL-PARTIAL",
        status="To Do",
        issue_type=None,
        priority="Medium",
        blocker_flag=False,
        created_at=partial_created_at,
    )
    _seed_issue(
        session,
        issue_key="LHPM-202",
        release_id="LHPM-REL-PARTIAL",
        status="To Do",
        issue_type="Bug",
        priority=None,
        blocker_flag=False,
        created_at=partial_created_at + timedelta(hours=1),
    )
    _seed_issue(
        session,
        issue_key="LHPM-203",
        release_id="LHPM-REL-PARTIAL",
        status=None,
        issue_type="Bug",
        priority="Critical",
        blocker_flag=False,
        created_at=partial_created_at + timedelta(hours=2),
    )
    _seed_issue(
        session,
        issue_key="LHPM-204",
        release_id="LHPM-REL-PARTIAL",
        status="To Do",
        issue_type="Story",
        priority=None,
        created_at=partial_created_at + timedelta(hours=3),
    )
    _seed_issue(
        session,
        issue_key="LHPM-205",
        release_id="LHPM-REL-PARTIAL",
        status="In Progress",
        issue_type="Story",
        priority="Medium",
        blocker_flag=True,
        created_at=partial_created_at + timedelta(hours=4),
    )
    session.commit()
    _recompute_release(session, "LHPM-REL-PARTIAL", SECOND_SNAPSHOT_AT)


@pytest.mark.parametrize(
    ("contract_id", "path"),
    [
        (
            "release.collection.project-scoped.200",
            "/releases?project_key=LHPM&skip=0&limit=1",
        ),
        (
            "release.metrics.populated.200",
            "/releases/LHPM-REL-ALPHA/metrics",
        ),
        (
            "release.metrics.incomplete-evidence.200",
            "/releases/LHPM-REL-PARTIAL/metrics",
        ),
        (
            "release.signal.stored.200",
            "/releases/LHPM-REL-ALPHA/signal",
        ),
        (
            "release.snapshot-comparison.200",
            "/releases/LHPM-REL-ALPHA/snapshot-comparison?baseline=previous",
        ),
    ],
    ids=[
        "collection",
        "metrics_populated",
        "metrics_incomplete",
        "signal",
        "comparison",
    ],
)
def test_release_payload_matches_contract(
    release_contract_client: TestClient,
    contract_id: str,
    path: str,
) -> None:
    response = release_contract_client.get(path)

    assert_api_contract_snapshot(
        contract_id,
        status_code=response.status_code,
        payload=response.json(),
    )
