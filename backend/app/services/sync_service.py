import asyncio
import logging
from dataclasses import asdict, dataclass, replace

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.repositories.operational_status_repository import OperationalStatusRepository
from app.repositories.sync_repository import SyncRepository
from app.services.analytics_service import AnalyticsService
from app.services.jira_errors import JiraServiceError
from app.services.jira_field_mapper import JiraFieldMapper
from app.services.jira_service import JiraService
from app.services.jira_types import JiraChangelogEntry, JiraIssueDetail, JiraIssueSummary, JiraSprintRef, JiraVersion
from app.services.signal_service import SignalService
from app.utils.error_sanitizer import sanitize_error_detail

logger = logging.getLogger(__name__)
_sync_lock = asyncio.Lock()


@dataclass
class SyncResult:
    project_key: str
    releases_fetched: int = 0
    releases_inserted: int = 0
    releases_updated: int = 0
    sprints_inserted: int = 0
    sprints_updated: int = 0
    issues_fetched: int = 0
    issues_inserted: int = 0
    issues_updated: int = 0
    issues_skipped: int = 0
    history_fetched: int = 0
    history_inserted: int = 0
    history_skipped: int = 0


class SyncServiceError(Exception):
    """Raised when sync prerequisites or orchestration fail."""


class SyncAlreadyRunningError(SyncServiceError):
    """Raised when a second Jira sync starts before the current one finishes."""


class SyncService:
    """Orchestrates deterministic Jira ingestion for a single configured project."""

    def __init__(
        self,
        jira_service: JiraService | None = None,
        settings: Settings | None = None,
    ) -> None:
        self._settings = settings or get_settings()
        self._field_mapper = JiraFieldMapper(self._settings)
        self._jira_service = jira_service or JiraService(settings=self._settings)

    def _validate_sync_settings(self) -> str:
        if not self._settings.jira_sync_enabled:
            raise SyncServiceError("Jira sync is disabled by configuration")
        try:
            self._settings.validate_startup_settings()
        except ValueError as exc:
            raise SyncServiceError(str(exc)) from exc
        return self._settings.jira_project_key.strip()

    async def _fetch_project_issues(self, project_key: str) -> list[JiraIssueSummary]:
        page_size = self._settings.jira_sync_page_size
        next_page_token: str | None = None
        all_issues: list[JiraIssueSummary] = []
        jql = f'project = "{project_key}" ORDER BY key ASC'

        while True:
            batch, next_page_token = await self._jira_service.search_issues(
                jql=jql,
                next_page_token=next_page_token,
                max_results=page_size,
            )
            all_issues.extend(batch)
            if next_page_token is None:
                break

        return all_issues

    def _is_blocker(
        self,
        issue_type: str | None,
        priority: str | None,
        status: str | None,
        blocker_flag: bool | None,
    ) -> bool:
        """Classify a blocker with the effective explicit-field and fallback rules."""
        return self._field_mapper.classify_blocker(
            issue_type=issue_type,
            severity=priority,
            status=status,
            blocker_flag=blocker_flag,
        )

    def _filter_relevant_history(self, entries: list[JiraChangelogEntry]) -> list[JiraChangelogEntry]:
        filtered: list[JiraChangelogEntry] = []
        for entry in entries:
            if self._field_mapper.is_relevant_history_field(entry.field_name):
                filtered.append(entry)
        return filtered

    def _sanitize_persisted_text(self, value: str | None) -> str | None:
        if value is None:
            return None
        sanitized = sanitize_error_detail(value, max_length=max(len(value) + 64, 280))
        for secret in {self._settings.jira_api_token.strip(), self._settings.lighthouse_api_token.strip()}:
            if secret:
                sanitized = sanitized.replace(secret, "[REDACTED]")
        return sanitized

    def _sanitize_sprint_ref(self, sprint_ref: JiraSprintRef) -> JiraSprintRef:
        return replace(
            sprint_ref,
            name=self._sanitize_persisted_text(sprint_ref.name) or "",
            goal=self._sanitize_persisted_text(sprint_ref.goal),
        )

    def _sanitize_version(self, version: JiraVersion) -> JiraVersion:
        return replace(
            version,
            name=self._sanitize_persisted_text(version.name) or "",
            description=self._sanitize_persisted_text(version.description),
        )

    def _sanitize_issue_detail(self, issue_detail: JiraIssueDetail) -> JiraIssueDetail:
        return replace(
            issue_detail,
            summary=self._sanitize_persisted_text(issue_detail.summary) or "",
            status=self._sanitize_persisted_text(issue_detail.status) or "",
            issue_type=self._sanitize_persisted_text(issue_detail.issue_type) or "",
            priority=self._sanitize_persisted_text(issue_detail.priority),
            assignee=self._sanitize_persisted_text(issue_detail.assignee),
            fix_versions=[self._sanitize_persisted_text(version) or "" for version in issue_detail.fix_versions],
            sprints=[self._sanitize_sprint_ref(sprint_ref) for sprint_ref in issue_detail.sprints],
        )

    def _sanitize_history_entry(self, entry: JiraChangelogEntry) -> JiraChangelogEntry:
        return replace(
            entry,
            field_name=self._sanitize_persisted_text(entry.field_name) or "",
            from_value=self._sanitize_persisted_text(entry.from_value),
            to_value=self._sanitize_persisted_text(entry.to_value),
        )

    async def sync_from_jira(self, session: Session) -> dict[str, int | str]:
        if _sync_lock.locked():
            raise SyncAlreadyRunningError("Jira sync is already running")

        async with _sync_lock:
            return await self._sync_from_jira_locked(session=session)

    async def _sync_from_jira_locked(self, session: Session) -> dict[str, int | str]:
        project_key = self._validate_sync_settings()
        result = SyncResult(project_key=project_key)
        recompute_release_count = 0
        sprint_ids_seen: set[str] = set()

        logger.info("jira_sync_started project_key=%s", project_key)

        try:
            await self._jira_service.validate_auth()
            versions = [self._sanitize_version(version) for version in await self._jira_service.get_project_versions(project_key=project_key)]
            result.releases_fetched = len(versions)

            version_name_to_release_id: dict[str, str] = {}
            for version in versions:
                _, created = SyncRepository.upsert_release(session=session, version=version)
                version_name_to_release_id[version.name] = version.id
                if created:
                    result.releases_inserted += 1
                else:
                    result.releases_updated += 1

            logger.info(
                "jira_sync_releases_processed project_key=%s releases_fetched=%d releases_inserted=%d releases_updated=%d",
                project_key,
                result.releases_fetched,
                result.releases_inserted,
                result.releases_updated,
            )

            issue_summaries = await self._fetch_project_issues(project_key=project_key)
            result.issues_fetched = len(issue_summaries)

            for issue_summary in issue_summaries:
                try:
                    issue_detail = self._sanitize_issue_detail(
                        await self._jira_service.get_issue_details(issue_key=issue_summary.key)
                    )
                except JiraServiceError:
                    result.issues_skipped += 1
                    logger.warning("Skipping issue %s due to detail fetch error", issue_summary.key)
                    continue

                # Assumption: when multiple fix versions exist we link to the first known
                # project version for deterministic single-release association in MVP.
                linked_release_id: str | None = None
                for version_name in issue_detail.fix_versions:
                    mapped_release_id = version_name_to_release_id.get(version_name)
                    if mapped_release_id:
                        linked_release_id = mapped_release_id
                        break

                linked_sprint_ids: list[str] = []
                for sprint_ref in issue_detail.sprints:
                    _, sprint_created = SyncRepository.upsert_sprint(
                        session=session,
                        sprint_ref=sprint_ref,
                        project_key=project_key,
                    )
                    linked_sprint_ids.append(sprint_ref.id)
                    sprint_ids_seen.add(sprint_ref.id)
                    if sprint_created:
                        result.sprints_inserted += 1
                    else:
                        result.sprints_updated += 1

                _, created = SyncRepository.upsert_issue(
                    session=session,
                    issue_detail=issue_detail,
                    release_id=linked_release_id,
                    is_blocker=self._is_blocker(
                        issue_type=issue_detail.issue_type,
                        priority=issue_detail.priority,
                        status=issue_detail.status,
                        blocker_flag=issue_detail.blocker_flag,
                    ),
                )
                if created:
                    result.issues_inserted += 1
                else:
                    result.issues_updated += 1

                SyncRepository.replace_issue_sprints(
                    session=session,
                    issue_key=issue_detail.key,
                    sprint_ids=linked_sprint_ids,
                )

                changelog_entries = await self._jira_service.get_issue_changelog(
                    issue_key=issue_summary.key,
                    start_at=0,
                    max_results=self._settings.jira_sync_changelog_page_size,
                )
                filtered_history = [
                    self._sanitize_history_entry(entry) for entry in self._filter_relevant_history(changelog_entries)
                ]
                result.history_fetched += len(filtered_history)
                inserted_count, skipped_count = SyncRepository.insert_issue_history_entries(
                    session=session,
                    entries=filtered_history,
                )
                result.history_inserted += inserted_count
                result.history_skipped += skipped_count
                SyncRepository.mark_issue_changelog_complete(
                    session=session,
                    issue_key=issue_detail.key,
                )

            logger.info(
                "jira_sync_issues_processed project_key=%s issues_fetched=%d issues_inserted=%d issues_updated=%d issues_skipped=%d",
                project_key,
                result.issues_fetched,
                result.issues_inserted,
                result.issues_updated,
                result.issues_skipped,
            )
            logger.info(
                "jira_sync_changelog_processed project_key=%s history_fetched=%d history_inserted=%d history_skipped=%d",
                project_key,
                result.history_fetched,
                result.history_inserted,
                result.history_skipped,
            )

            # Keep metrics snapshots in sync with each successful Jira ingestion run.
            analytics_service = AnalyticsService()
            signal_service = SignalService()
            for release_id in version_name_to_release_id.values():
                analytics_service.recompute_release_metrics(session=session, release_id=release_id)
                signal_service.recompute_release_signal(session=session, release_id=release_id)
                recompute_release_count += 1
            for sprint_id in sorted(sprint_ids_seen):
                analytics_service.recompute_sprint_metrics(session=session, sprint_id=sprint_id)

            logger.info(
                "jira_sync_recompute_processed project_key=%s releases_recomputed=%d sprints_recomputed=%d",
                project_key,
                recompute_release_count,
                len(sprint_ids_seen),
            )

            OperationalStatusRepository.mark_sync_succeeded(session=session)

            session.commit()
        except JiraServiceError as exc:
            session.rollback()
            self._persist_sync_failure_status(session=session, exc=exc)
            raise SyncServiceError(f"Jira sync failed: {exc}") from exc
        except ValueError as exc:
            session.rollback()
            self._persist_sync_failure_status(session=session, exc=exc)
            raise SyncServiceError(f"Post-sync recompute failed: {exc}") from exc
        except SQLAlchemyError as exc:
            session.rollback()
            self._persist_sync_failure_status(session=session, exc=exc)
            raise SyncServiceError(f"Database sync failed: {exc}") from exc
        except Exception as exc:  # noqa: BLE001
            session.rollback()
            self._persist_sync_failure_status(session=session, exc=exc)
            raise SyncServiceError(f"Unexpected sync failure: {type(exc).__name__}") from exc

        logger.info(
            "jira_sync_completed project_key=%s releases_fetched=%d releases_inserted=%d "
            "releases_updated=%d issues_fetched=%d issues_inserted=%d issues_updated=%d "
            "issues_skipped=%d history_fetched=%d history_inserted=%d history_skipped=%d",
            result.project_key,
            result.releases_fetched,
            result.releases_inserted,
            result.releases_updated,
            result.issues_fetched,
            result.issues_inserted,
            result.issues_updated,
            result.issues_skipped,
            result.history_fetched,
            result.history_inserted,
            result.history_skipped,
        )
        return asdict(result)

    @staticmethod
    def _persist_sync_failure_status(session: Session, exc: Exception) -> None:
        failure_summary = sanitize_error_detail(f"{type(exc).__name__}: {exc}")
        try:
            OperationalStatusRepository.mark_sync_failed(
                session=session,
                failure_summary=failure_summary,
            )
            session.commit()
        except SQLAlchemyError as persist_exc:
            session.rollback()
            logger.warning("jira_sync_failure_status_persist_failed error=%s", persist_exc)
