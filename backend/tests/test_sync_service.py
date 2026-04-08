from datetime import UTC, datetime

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.config import Settings
from app.db.base import Base
from app.models import Issue, IssueHistory, Release
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
        start_at: int = 0,
        max_results: int = 50,
        fields: list[str] | None = None,
    ) -> list[JiraIssueSummary]:
        if start_at > 0:
            return []
        return [
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
        ]

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

    assert len(releases) == 1
    assert len(issues) == 1
    assert len(history) == 1
    assert issues[0].release_id == "1001"


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
    assert len(history) == 1
