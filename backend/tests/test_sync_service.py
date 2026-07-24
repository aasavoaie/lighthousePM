import asyncio
from datetime import UTC, datetime

import pytest
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.config import Settings
from app.db.base import Base
from app.models import (
    Issue,
    IssueHistory,
    JiraProjectSyncState,
    MetricSnapshot,
    OperationalStatus,
    Release,
    ReleaseSignal,
)
from app.services.jira_errors import JiraAuthError
from app.services.jira_types import JiraChangelogEntry, JiraIssueDetail, JiraIssueSummary, JiraVersion
from app.services.sync_service import SyncService, SyncServiceError


class FakeJiraService:
    jira_created_at = datetime(2026, 3, 15, 8, 0, tzinfo=UTC)
    jira_updated_at = datetime(2026, 4, 1, 10, 0, tzinfo=UTC)

    async def validate_auth(self) -> None:
        return None

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
                    updated=self.jira_updated_at,
                    assignee_id="jira-alice",
                    created=self.jira_created_at,
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
            updated=self.jira_updated_at,
            assignee_id="jira-alice",
            created=self.jira_created_at,
            fix_versions=["Release 1"],
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
            ),
            JiraChangelogEntry(
                issue_key=issue_key,
                field_name="summary",
                from_value="Old",
                to_value="New",
                changed_at=datetime(2026, 4, 2, tzinfo=UTC),
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
async def test_sync_from_jira_returns_clear_error_when_manual_sync_disabled(db_session: Session) -> None:
    class UnexpectedJiraService(FakeJiraService):
        async def validate_auth(self) -> None:
            raise AssertionError("Jira should not be called when manual sync is disabled")

    settings = _test_settings()
    settings.jira_sync_enabled = False
    service = SyncService(jira_service=UnexpectedJiraService(), settings=settings)

    with pytest.raises(SyncServiceError, match="Jira sync is disabled by configuration"):
        await service.sync_from_jira(session=db_session)


@pytest.mark.asyncio
async def test_sync_from_jira_allows_manual_sync_when_scheduler_is_disabled(db_session: Session) -> None:
    settings = _test_settings()
    settings.jira_sync_enabled = True
    settings.jira_sync_interval_seconds = 0
    service = SyncService(jira_service=FakeJiraService(), settings=settings)

    result = await service.sync_from_jira(session=db_session)

    assert result["project_key"] == "LHPM"
    assert result["releases_fetched"] == 1
    assert result["issues_fetched"] == 1


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
    assert {signal.metric_snapshot_id for signal in signals} == {snapshot.id for snapshot in snapshots}
    assert all(signal.ruleset_version == 2 for signal in signals)
    assert signals[0].signal == "INCONCLUSIVE"
    assert signals[0].confidence_score is None
    assert any("reopen_rate_pct" in reason for reason in signals[0].reasons)
    assert issues[0].release_id == "1001"
    assert issues[0].story_points == 5.0
    assert issues[0].jira_assignee_id == "jira-alice"
    assert issues[0].jira_created_at == FakeJiraService.jira_created_at.replace(tzinfo=None)
    assert issues[0].jira_updated_at == FakeJiraService.jira_updated_at.replace(tzinfo=None)
    assert issues[0].jira_changelog_complete is True
    sync_state = db_session.scalar(select(JiraProjectSyncState))
    assert sync_state is not None
    assert sync_state.project_key == "LHPM"
    assert sync_state.current_sync_status == "succeeded"
    assert sync_state.last_successful_jira_updated_at == (
        FakeJiraService.jira_updated_at.replace(tzinfo=None)
    )
    assert sync_state.last_successful_sync_at is not None
    assert sync_state.last_failure_summary is None
    assert sync_state.latest_sync_result is not None
    assert sync_state.latest_sync_result["issues_inserted"] == 1

    status = db_session.scalar(select(OperationalStatus))
    assert status is not None
    assert status.last_sync_succeeded_at is not None
    assert status.last_sync_failure_summary is None


@pytest.mark.asyncio
async def test_sync_from_jira_rejects_concurrent_sync(db_session: Session) -> None:
    sync_started = asyncio.Event()
    release_sync = asyncio.Event()

    class SlowJiraService(FakeJiraService):
        async def validate_auth(self) -> None:
            sync_started.set()
            await release_sync.wait()

    first_service = SyncService(jira_service=SlowJiraService(), settings=_test_settings())
    second_service = SyncService(jira_service=FakeJiraService(), settings=_test_settings())

    first_task = asyncio.create_task(first_service.sync_from_jira(session=db_session))
    await sync_started.wait()

    with pytest.raises(SyncServiceError, match="Jira sync is already running"):
        await second_service.sync_from_jira(session=db_session)

    release_sync.set()
    await first_task


@pytest.mark.asyncio
async def test_sync_from_jira_redacts_configured_secret_before_sqlite_persistence(db_session: Session) -> None:
    settings = _test_settings()
    settings.jira_api_token = "persist-secret"

    class SecretEchoJiraService(FakeJiraService):
        async def get_project_versions(self, project_key: str) -> list[JiraVersion]:
            versions = await super().get_project_versions(project_key=project_key)
            versions[0].description = "Release copied persist-secret"
            return versions

        async def get_issue_details(self, issue_key: str, fields: list[str] | None = None) -> JiraIssueDetail:
            detail = await super().get_issue_details(issue_key=issue_key, fields=fields)
            detail.summary = "Issue copied persist-secret"
            return detail

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
                    to_value="Done with persist-secret",
                    changed_at=datetime(2026, 4, 1, tzinfo=UTC),
                )
            ]

    service = SyncService(jira_service=SecretEchoJiraService(), settings=settings)

    await service.sync_from_jira(session=db_session)

    rows = db_session.execute(
        text(
            """
            SELECT summary AS value FROM issues
            UNION ALL SELECT description FROM releases
            UNION ALL SELECT old_value FROM issue_history
            UNION ALL SELECT new_value FROM issue_history
            """
        )
    ).all()
    stored_text = "\n".join(str(row.value) for row in rows if row.value is not None)
    assert "persist-secret" not in stored_text
    assert "[REDACTED]" in stored_text


@pytest.mark.asyncio
async def test_sync_from_jira_is_idempotent_for_history_entries(db_session: Session) -> None:
    service = SyncService(jira_service=FakeJiraService(), settings=_test_settings())

    first = await service.sync_from_jira(session=db_session)
    second = await service.sync_from_jira(session=db_session)

    assert first["issues_inserted"] == 1
    assert second["issues_inserted"] == 0
    assert second["issues_updated"] == 0
    assert second["issue_details_skipped_unchanged"] == 1
    assert second["history_inserted"] == 0
    assert second["history_skipped"] == 0
    assert second["changelogs_skipped_unchanged"] == 1

    history = list(db_session.scalars(select(IssueHistory)).all())
    snapshots = list(db_session.scalars(select(MetricSnapshot)).all())
    signals = list(db_session.scalars(select(ReleaseSignal)).all())
    assert len(history) == 1
    assert len(snapshots) == 2
    assert len(signals) == 2
    assert {signal.metric_snapshot_id for signal in signals} == {snapshot.id for snapshot in snapshots}
    assert all(signal.ruleset_version == 2 for signal in signals)


@pytest.mark.asyncio
async def test_sync_from_jira_advances_project_cursor_from_changed_issue_timestamp(
    db_session: Session,
) -> None:
    class MutableUpdatedJiraService(FakeJiraService):
        def __init__(self) -> None:
            self.updated = datetime(2026, 4, 1, 10, 0, tzinfo=UTC)

        async def search_issues(
            self,
            jql: str,
            next_page_token: str | None = None,
            max_results: int = 50,
            fields: list[str] | None = None,
        ) -> tuple[list[JiraIssueSummary], str | None]:
            issues, token = await super().search_issues(
                jql=jql,
                next_page_token=next_page_token,
                max_results=max_results,
                fields=fields,
            )
            for issue in issues:
                issue.updated = self.updated
            return issues, token

        async def get_issue_details(self, issue_key: str, fields: list[str] | None = None) -> JiraIssueDetail:
            detail = await super().get_issue_details(issue_key=issue_key, fields=fields)
            detail.updated = self.updated
            return detail

    jira_service = MutableUpdatedJiraService()
    service = SyncService(jira_service=jira_service, settings=_test_settings())

    await service.sync_from_jira(session=db_session)
    jira_service.updated = datetime(2026, 4, 3, 12, 30, tzinfo=UTC)
    await service.sync_from_jira(session=db_session)

    sync_state = db_session.scalar(select(JiraProjectSyncState))
    assert sync_state is not None
    assert sync_state.last_successful_jira_updated_at == (
        jira_service.updated.replace(tzinfo=None)
    )


@pytest.mark.asyncio
async def test_sync_from_jira_failure_preserves_project_cursor(db_session: Session) -> None:
    service = SyncService(jira_service=FakeJiraService(), settings=_test_settings())
    await service.sync_from_jira(session=db_session)
    original_sync_state = db_session.scalar(select(JiraProjectSyncState))
    assert original_sync_state is not None
    original_cursor = original_sync_state.last_successful_jira_updated_at
    original_success_time = original_sync_state.last_successful_sync_at

    class FailingJiraService(FakeJiraService):
        async def get_project_versions(self, project_key: str) -> list[JiraVersion]:
            raise RuntimeError("Jira unavailable")

    failing_service = SyncService(jira_service=FailingJiraService(), settings=_test_settings())

    with pytest.raises(SyncServiceError, match="Unexpected sync failure"):
        await failing_service.sync_from_jira(session=db_session)

    sync_state = db_session.scalar(select(JiraProjectSyncState))
    assert sync_state is not None
    assert sync_state.last_successful_jira_updated_at == original_cursor
    assert sync_state.last_successful_sync_at == original_success_time


@pytest.mark.asyncio
async def test_sync_from_jira_skips_unchanged_existing_issue_detail_and_changelog(
    db_session: Session,
) -> None:
    class CountingJiraService(FakeJiraService):
        def __init__(self) -> None:
            self.detail_calls = 0
            self.changelog_calls = 0

        async def get_issue_details(
            self,
            issue_key: str,
            fields: list[str] | None = None,
        ) -> JiraIssueDetail:
            self.detail_calls += 1
            return await super().get_issue_details(issue_key=issue_key, fields=fields)

        async def get_issue_changelog(
            self,
            issue_key: str,
            start_at: int = 0,
            max_results: int = 100,
        ) -> list[JiraChangelogEntry]:
            self.changelog_calls += 1
            return await super().get_issue_changelog(
                issue_key=issue_key,
                start_at=start_at,
                max_results=max_results,
            )

    await SyncService(jira_service=FakeJiraService(), settings=_test_settings()).sync_from_jira(
        session=db_session
    )
    jira_service = CountingJiraService()
    service = SyncService(jira_service=jira_service, settings=_test_settings())

    result = await service.sync_from_jira(session=db_session)

    assert result["issue_details_skipped_unchanged"] == 1
    assert result["changelogs_skipped_unchanged"] == 1
    assert result["issues_updated"] == 0
    assert result["history_fetched"] == 0
    assert jira_service.detail_calls == 0
    assert jira_service.changelog_calls == 0


@pytest.mark.asyncio
async def test_sync_from_jira_fetches_changed_issue_after_cursor(
    db_session: Session,
) -> None:
    class ChangedJiraService(FakeJiraService):
        jira_updated_at = datetime(2026, 4, 2, 11, 0, tzinfo=UTC)

        def __init__(self) -> None:
            self.detail_calls = 0
            self.changelog_calls = 0

        async def get_issue_details(
            self,
            issue_key: str,
            fields: list[str] | None = None,
        ) -> JiraIssueDetail:
            self.detail_calls += 1
            return await super().get_issue_details(issue_key=issue_key, fields=fields)

        async def get_issue_changelog(
            self,
            issue_key: str,
            start_at: int = 0,
            max_results: int = 100,
        ) -> list[JiraChangelogEntry]:
            self.changelog_calls += 1
            return await super().get_issue_changelog(
                issue_key=issue_key,
                start_at=start_at,
                max_results=max_results,
            )

    await SyncService(jira_service=FakeJiraService(), settings=_test_settings()).sync_from_jira(
        session=db_session
    )
    jira_service = ChangedJiraService()
    service = SyncService(jira_service=jira_service, settings=_test_settings())

    result = await service.sync_from_jira(session=db_session)

    assert result["issue_details_skipped_unchanged"] == 0
    assert result["changelogs_skipped_unchanged"] == 0
    assert result["issues_updated"] == 1
    assert jira_service.detail_calls == 1
    assert jira_service.changelog_calls == 1


@pytest.mark.asyncio
async def test_sync_from_jira_fetches_unchanged_issue_missing_locally(
    db_session: Session,
) -> None:
    class CountingJiraService(FakeJiraService):
        def __init__(self) -> None:
            self.detail_calls = 0
            self.changelog_calls = 0

        async def get_issue_details(
            self,
            issue_key: str,
            fields: list[str] | None = None,
        ) -> JiraIssueDetail:
            self.detail_calls += 1
            return await super().get_issue_details(issue_key=issue_key, fields=fields)

        async def get_issue_changelog(
            self,
            issue_key: str,
            start_at: int = 0,
            max_results: int = 100,
        ) -> list[JiraChangelogEntry]:
            self.changelog_calls += 1
            return await super().get_issue_changelog(
                issue_key=issue_key,
                start_at=start_at,
                max_results=max_results,
            )

    db_session.add(
        JiraProjectSyncState(
            project_key="LHPM",
            last_successful_jira_updated_at=FakeJiraService.jira_updated_at,
            last_successful_sync_at=datetime(2026, 4, 1, 10, 5, tzinfo=UTC),
        )
    )
    db_session.flush()
    jira_service = CountingJiraService()
    service = SyncService(jira_service=jira_service, settings=_test_settings())

    result = await service.sync_from_jira(session=db_session)

    assert result["issue_details_skipped_unchanged"] == 0
    assert result["changelogs_skipped_unchanged"] == 0
    assert result["issues_inserted"] == 1
    assert jira_service.detail_calls == 1
    assert jira_service.changelog_calls == 1


@pytest.mark.asyncio
async def test_sync_from_jira_fetches_when_local_issue_timestamp_missing(
    db_session: Session,
) -> None:
    class CountingJiraService(FakeJiraService):
        def __init__(self) -> None:
            self.detail_calls = 0
            self.changelog_calls = 0

        async def get_issue_details(
            self,
            issue_key: str,
            fields: list[str] | None = None,
        ) -> JiraIssueDetail:
            self.detail_calls += 1
            return await super().get_issue_details(issue_key=issue_key, fields=fields)

        async def get_issue_changelog(
            self,
            issue_key: str,
            start_at: int = 0,
            max_results: int = 100,
        ) -> list[JiraChangelogEntry]:
            self.changelog_calls += 1
            return await super().get_issue_changelog(
                issue_key=issue_key,
                start_at=start_at,
                max_results=max_results,
            )

    await SyncService(jira_service=FakeJiraService(), settings=_test_settings()).sync_from_jira(
        session=db_session
    )
    issue = db_session.scalar(select(Issue).where(Issue.issue_key == "LHPM-1"))
    assert issue is not None
    issue.jira_updated_at = None
    db_session.flush()
    jira_service = CountingJiraService()
    service = SyncService(jira_service=jira_service, settings=_test_settings())

    result = await service.sync_from_jira(session=db_session)

    assert result["issue_details_skipped_unchanged"] == 0
    assert result["changelogs_skipped_unchanged"] == 0
    assert result["issues_updated"] == 1
    assert jira_service.detail_calls == 1
    assert jira_service.changelog_calls == 1


@pytest.mark.asyncio
async def test_sync_from_jira_fetches_when_local_changelog_incomplete(
    db_session: Session,
) -> None:
    class CountingJiraService(FakeJiraService):
        def __init__(self) -> None:
            self.detail_calls = 0
            self.changelog_calls = 0

        async def get_issue_details(
            self,
            issue_key: str,
            fields: list[str] | None = None,
        ) -> JiraIssueDetail:
            self.detail_calls += 1
            return await super().get_issue_details(issue_key=issue_key, fields=fields)

        async def get_issue_changelog(
            self,
            issue_key: str,
            start_at: int = 0,
            max_results: int = 100,
        ) -> list[JiraChangelogEntry]:
            self.changelog_calls += 1
            return await super().get_issue_changelog(
                issue_key=issue_key,
                start_at=start_at,
                max_results=max_results,
            )

    await SyncService(jira_service=FakeJiraService(), settings=_test_settings()).sync_from_jira(
        session=db_session
    )
    issue = db_session.scalar(select(Issue).where(Issue.issue_key == "LHPM-1"))
    assert issue is not None
    issue.jira_changelog_complete = False
    db_session.flush()
    jira_service = CountingJiraService()
    service = SyncService(jira_service=jira_service, settings=_test_settings())

    result = await service.sync_from_jira(session=db_session)

    assert result["issue_details_skipped_unchanged"] == 0
    assert result["changelogs_skipped_unchanged"] == 0
    assert result["issues_updated"] == 1
    assert jira_service.detail_calls == 1
    assert jira_service.changelog_calls == 1


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
    sync_state = db_session.scalar(select(JiraProjectSyncState))
    assert sync_state is not None
    assert sync_state.current_sync_status == "failed"
    assert sync_state.last_failed_sync_at is not None
    assert sync_state.last_failure_summary is not None
    assert "verysecret" not in sync_state.last_failure_summary


@pytest.mark.asyncio
async def test_sync_from_jira_marks_project_status_running_while_active(
    db_session: Session,
) -> None:
    sync_started = asyncio.Event()
    release_sync = asyncio.Event()

    class SlowJiraService(FakeJiraService):
        async def validate_auth(self) -> None:
            sync_started.set()
            await release_sync.wait()

    service = SyncService(jira_service=SlowJiraService(), settings=_test_settings())

    sync_task = asyncio.create_task(service.sync_from_jira(session=db_session))
    await sync_started.wait()

    sync_state = db_session.scalar(select(JiraProjectSyncState))
    assert sync_state is not None
    assert sync_state.current_sync_status == "running"

    release_sync.set()
    await sync_task


def test_get_jira_sync_status_reports_idle_without_project_state(
    db_session: Session,
) -> None:
    service = SyncService(jira_service=FakeJiraService(), settings=_test_settings())

    status = service.get_jira_sync_status(session=db_session)

    assert status["project_key"] == "LHPM"
    assert status["current_sync_status"] == "idle"
    assert status["latest_sync_result"] is None


def test_get_jira_sync_status_does_not_report_stale_running_as_active(
    db_session: Session,
) -> None:
    db_session.add(
        JiraProjectSyncState(
            project_key="LHPM",
            current_sync_status="running",
            last_successful_sync_at=datetime(2026, 4, 1, 10, 5, tzinfo=UTC),
        )
    )
    db_session.flush()
    service = SyncService(jira_service=FakeJiraService(), settings=_test_settings())

    status = service.get_jira_sync_status(session=db_session)

    assert status["current_sync_status"] == "failed"
    assert status["last_failure_summary"] == "Previous sync did not finish."


@pytest.mark.asyncio
async def test_sync_from_jira_validates_auth_before_fetching_versions(db_session: Session) -> None:
    class AuthFailingJiraService(FakeJiraService):
        async def validate_auth(self) -> None:
            raise JiraAuthError("bad token")

        async def get_project_versions(self, project_key: str) -> list[JiraVersion]:
            raise AssertionError("versions should not be fetched when auth fails")

    service = SyncService(jira_service=AuthFailingJiraService(), settings=_test_settings())

    with pytest.raises(SyncServiceError, match="Jira sync failed"):
        await service.sync_from_jira(session=db_session)

    status = db_session.scalar(select(OperationalStatus))
    assert status is not None
    assert status.last_sync_failed_at is not None
    assert status.last_sync_failure_summary is not None
    assert "bad token" in status.last_sync_failure_summary


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
                fix_versions=["Release 1"],
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
async def test_sync_from_jira_classifies_blocked_status_as_blocker(db_session: Session) -> None:
    class BlockedStatusJiraService(FakeJiraService):
        async def get_issue_details(self, issue_key: str, fields: list[str] | None = None) -> JiraIssueDetail:
            return JiraIssueDetail(
                key=issue_key,
                summary="Blocked work",
                status="Blocked",
                issue_type="Story",
                priority="Medium",
                assignee="alice",
                updated=datetime.now(UTC),
                fix_versions=["Release 1"],
                story_points=3.0,
            )

    service = SyncService(jira_service=BlockedStatusJiraService(), settings=_test_settings())

    await service.sync_from_jira(session=db_session)

    stored_issue = db_session.scalar(select(Issue).where(Issue.issue_key == "LHPM-1"))
    assert stored_issue is not None
    assert stored_issue.is_blocker is True


@pytest.mark.asyncio
async def test_sync_from_jira_updates_story_points(db_session: Session) -> None:
    class MutableStoryPointJiraService(FakeJiraService):
        def __init__(self) -> None:
            self.story_points = 3.0
            self.updated = datetime(2026, 4, 1, 10, 0, tzinfo=UTC)

        async def search_issues(
            self,
            jql: str,
            next_page_token: str | None = None,
            max_results: int = 50,
            fields: list[str] | None = None,
        ) -> tuple[list[JiraIssueSummary], str | None]:
            issues, token = await super().search_issues(
                jql=jql,
                next_page_token=next_page_token,
                max_results=max_results,
                fields=fields,
            )
            for issue in issues:
                issue.updated = self.updated
            return issues, token

        async def get_issue_details(self, issue_key: str, fields: list[str] | None = None) -> JiraIssueDetail:
            detail = await super().get_issue_details(issue_key=issue_key, fields=fields)
            detail.story_points = self.story_points
            detail.updated = self.updated
            return detail

    jira_service = MutableStoryPointJiraService()
    service = SyncService(jira_service=jira_service, settings=_test_settings())

    await service.sync_from_jira(session=db_session)
    jira_service.story_points = 8.0
    jira_service.updated = datetime(2026, 4, 2, 10, 0, tzinfo=UTC)
    await service.sync_from_jira(session=db_session)

    stored_issue = db_session.scalar(select(Issue).where(Issue.issue_key == "LHPM-1"))
    assert stored_issue is not None
    assert stored_issue.story_points == 8.0
