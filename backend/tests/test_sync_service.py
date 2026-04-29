from datetime import UTC, datetime

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.config import Settings
from app.db.base import Base
from app.models import Issue, IssueHistory, MetricSnapshot, OperationalStatus, Release, ReleaseSignal
from app.services.jira_types import JiraChangelogEntry, JiraIssueDetail, JiraIssueSummary, JiraVersion
from app.services.sync_service import SyncService


class FakeJiraService:
    async def get_project_versions(self, project_key: str) -> list[JiraVersion]:
        return [
            JiraVersion(
                id="1001",
                name="Release 1",
                project_key=project_key,
                released=False,
                release_date="2026-04-30",
                start_date="2026-04-01",
                description="Release 1",
            )
        ]

    async def search_issues(
        self,
        jql: str,
        next_page_token: str | None = None,
        max_results: int = 50,
        fields: list[str] | None = None,
    ) -> tuple[list[JiraIssueSummary], str | None]:
        if next_page_token is not None:
            return ([], None)
        return (
            [
                JiraIssueSummary(
                    key="LHPM-1",
                    summary="Fix login bug",
                    status="In Progress",
                    issue_type="Bug",
                    priority="High",
                    assignee="alice",
                    updated=datetime.now(UTC),
                    fix_versions=["Release 1"],
                )
            ],
            None,
        )

    async def get_issue_details(self, issue_key: str, fields: list[str] | None = None) -> JiraIssueDetail:
        return JiraIssueDetail(
            key=issue_key,
            summary="Fix login bug",
            status="In Progress",
            issue_type="Bug",
            priority="High",
            assignee="alice",
            updated=datetime.now(UTC),
            description="details",
            labels=["backend"],
            components=["api"],
            fix_versions=["Release 1"],
            reporter="bob",
            story_points=5.0,
        )

    async def get_issue_changelog(
        self,
        issue_key: str,
        start_at: int = 0,
        max_results: int = 100,
    ) -> list[JiraChangelogEntry]:
        return [
            JiraChangelogEntry(
                issue_key=issue_key,
                field_name="status",
                from_value="To Do",
                to_value="In Progress",
                changed_at=datetime(2026, 4, 1, tzinfo=UTC),
                author="alice",
            ),
            JiraChangelogEntry(
                issue_key=issue_key,
                field_name="summary",
                from_value="Old",
                to_value="New",
                changed_at=datetime(2026, 4, 2, tzinfo=UTC),
                author="alice",
            ),
        ]


@pytest.fixture
def db_session() -> Session:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, class_=Session)
    Base.metadata.create_all(bind=engine)
    with TestingSessionLocal() as session:
        yield session


def _test_settings() -> Settings:
    return Settings(
        app_env="test",
        database_url="sqlite:///:memory:",
        jira_base_url="https://test.atlassian.net",
        jira_user_email="test@example.com",
        jira_api_token="token",
        jira_project_key="LHPM",
        jira_sync_enabled=True,
        jira_sync_page_size=50,
        jira_sync_changelog_page_size=100,
    )


@pytest.mark.asyncio
async def test_sync_from_jira_inserts_data_and_counts(db_session: Session) -> None:
    service = SyncService(jira_service=FakeJiraService(), settings=_test_settings())

    result = await service.sync_from_jira(session=db_session)

    assert result["project_key"] == "LHPM"
    assert result["releases_fetched"] == 1
    assert result["releases_inserted"] == 1
    assert result["issues_fetched"] == 1
    assert result["issues_inserted"] == 1
    assert result["history_fetched"] == 1
    assert result["history_inserted"] == 1
    assert result["history_skipped"] == 0

    releases = list(db_session.scalars(select(Release)).all())
    issues = list(db_session.scalars(select(Issue)).all())
    history = list(db_session.scalars(select(IssueHistory)).all())
    snapshots = list(db_session.scalars(select(MetricSnapshot)).all())
    signals = list(db_session.scalars(select(ReleaseSignal)).all())

    assert len(releases) == 1
    assert len(issues) == 1
    assert len(history) == 1
    assert len(snapshots) == 1
    assert len(signals) == 1
    assert signals[0].signal == "YELLOW"
    assert issues[0].release_id == "1001"
    assert issues[0].story_points == 5.0

    status = db_session.scalar(select(OperationalStatus))
    assert status is not None
    assert status.last_sync_succeeded_at is not None
    assert status.last_sync_failure_summary is None


@pytest.mark.asyncio
async def test_sync_from_jira_is_idempotent_for_history_entries(db_session: Session) -> None:
    service = SyncService(jira_service=FakeJiraService(), settings=_test_settings())

    first = await service.sync_from_jira(session=db_session)
    second = await service.sync_from_jira(session=db_session)

    assert first["issues_inserted"] == 1
    assert second["issues_inserted"] == 0
    assert second["issues_updated"] == 1
    assert second["history_inserted"] == 0
    assert second["history_skipped"] == 1

    history = list(db_session.scalars(select(IssueHistory)).all())
    snapshots = list(db_session.scalars(select(MetricSnapshot)).all())
    signals = list(db_session.scalars(select(ReleaseSignal)).all())
    assert len(history) == 1
    assert len(snapshots) == 2
    assert len(signals) == 1


@pytest.mark.asyncio
async def test_sync_from_jira_persists_failed_status(db_session: Session) -> None:
    class FailingJiraService(FakeJiraService):
        async def get_project_versions(self, project_key: str) -> list[JiraVersion]:
            raise RuntimeError("api_token=verysecret")

    service = SyncService(jira_service=FailingJiraService(), settings=_test_settings())

    with pytest.raises(Exception):
        await service.sync_from_jira(session=db_session)

    status = db_session.scalar(select(OperationalStatus))
    assert status is not None
    assert status.last_sync_failed_at is not None
    assert status.last_sync_failure_summary is not None
    assert "verysecret" not in status.last_sync_failure_summary


@pytest.mark.asyncio
async def test_sync_from_jira_uses_blocker_flag_when_present(db_session: Session) -> None:
    class BlockerFlagJiraService(FakeJiraService):
        async def get_issue_details(self, issue_key: str, fields: list[str] | None = None) -> JiraIssueDetail:
            return JiraIssueDetail(
                key=issue_key,
                summary="Flagged blocker",
                status="In Progress",
                issue_type="Story",
                priority="Low",
                assignee="alice",
                updated=datetime.now(UTC),
                description="details",
                labels=["backend"],
                components=["api"],
                fix_versions=["Release 1"],
                reporter="bob",
                blocker_flag=True,
            )

    settings = Settings(
        app_env="test",
        database_url="sqlite:///:memory:",
        jira_base_url="https://test.atlassian.net",
        jira_user_email="test@example.com",
        jira_api_token="token",
        jira_project_key="LHPM",
        jira_sync_enabled=True,
        jira_field_blocker="customfield_blocker",
    )
    service = SyncService(jira_service=BlockerFlagJiraService(), settings=settings)

    await service.sync_from_jira(session=db_session)

    stored_issue = db_session.scalar(select(Issue).where(Issue.issue_key == "LHPM-1"))
    assert stored_issue is not None
    assert stored_issue.is_blocker is True


@pytest.mark.asyncio
async def test_sync_from_jira_updates_story_points(db_session: Session) -> None:
    class MutableStoryPointJiraService(FakeJiraService):
        def __init__(self) -> None:
            self.story_points = 3.0

        async def get_issue_details(self, issue_key: str, fields: list[str] | None = None) -> JiraIssueDetail:
            detail = await super().get_issue_details(issue_key=issue_key, fields=fields)
            detail.story_points = self.story_points
            return detail

    jira_service = MutableStoryPointJiraService()
    service = SyncService(jira_service=jira_service, settings=_test_settings())

    await service.sync_from_jira(session=db_session)
    jira_service.story_points = 8.0
    await service.sync_from_jira(session=db_session)

    stored_issue = db_session.scalar(select(Issue).where(Issue.issue_key == "LHPM-1"))
    assert stored_issue is not None
    assert stored_issue.story_points == 8.0
