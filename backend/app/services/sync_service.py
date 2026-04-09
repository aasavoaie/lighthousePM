import logging
from dataclasses import asdict, dataclass

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.repositories.sync_repository import SyncRepository
from app.services.analytics_service import AnalyticsService
from app.services.jira_errors import JiraServiceError
from app.services.jira_service import JiraService
from app.services.jira_types import JiraChangelogEntry, JiraIssueSummary
from app.services.signal_service import SignalService

logger = logging.getLogger(__name__)

_RELEVANT_CHANGE_FIELDS = {"status", "assignee", "priority", "fix version", "fixversion"}


@dataclass
class SyncResult:
    project_key: str
    releases_fetched: int = 0
    releases_inserted: int = 0
    releases_updated: int = 0
    issues_fetched: int = 0
    issues_inserted: int = 0
    issues_updated: int = 0
    issues_skipped: int = 0
    history_fetched: int = 0
    history_inserted: int = 0
    history_skipped: int = 0


class SyncServiceError(Exception):
    """Raised when sync prerequisites or orchestration fail."""


class SyncService:
    """Orchestrates deterministic Jira ingestion for a single configured project."""

    def __init__(
        self,
        jira_service: JiraService | None = None,
        settings: Settings | None = None,
    ) -> None:
        self._settings = settings or get_settings()
        self._jira_service = jira_service or JiraService(settings=self._settings)

    def _validate_sync_settings(self) -> str:
        if not self._settings.jira_sync_enabled:
            raise SyncServiceError("Jira sync is disabled by configuration")
        if not self._settings.jira_project_key.strip():
            raise SyncServiceError("JIRA_PROJECT_KEY must be configured for sync")
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

    @staticmethod
    def _is_blocker(issue_type: str, priority: str | None, status: str) -> bool:
        """Temporary deterministic blocker heuristic for MVP sync.

        Assumption: blocker-like work is identified by issue type or priority labels
        because custom Jira fields vary between projects and are not yet standardized.
        """
        issue_type_value = issue_type.lower()
        priority_value = (priority or "").lower()
        status_value = status.lower()
        return (
            issue_type_value in {"blocker", "incident"}
            or priority_value in {"blocker", "highest", "critical"}
        ) and status_value not in {"done", "closed", "resolved"}

    @staticmethod
    def _filter_relevant_history(entries: list[JiraChangelogEntry]) -> list[JiraChangelogEntry]:
        filtered: list[JiraChangelogEntry] = []
        for entry in entries:
            normalized = entry.field_name.strip().lower()
            if normalized in _RELEVANT_CHANGE_FIELDS:
                filtered.append(entry)
        return filtered

    async def sync_from_jira(self, session: Session) -> dict[str, int | str]:
        project_key = self._validate_sync_settings()
        result = SyncResult(project_key=project_key)

        try:
            versions = await self._jira_service.get_project_versions(project_key=project_key)
            result.releases_fetched = len(versions)

            version_name_to_release_id: dict[str, str] = {}
            for version in versions:
                _, created = SyncRepository.upsert_release(session=session, version=version)
                version_name_to_release_id[version.name] = version.id
                if created:
                    result.releases_inserted += 1
                else:
                    result.releases_updated += 1

            issue_summaries = await self._fetch_project_issues(project_key=project_key)
            result.issues_fetched = len(issue_summaries)

            for issue_summary in issue_summaries:
                try:
                    issue_detail = await self._jira_service.get_issue_details(issue_key=issue_summary.key)
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

                _, created = SyncRepository.upsert_issue(
                    session=session,
                    issue_detail=issue_detail,
                    release_id=linked_release_id,
                    is_blocker=self._is_blocker(
                        issue_type=issue_detail.issue_type,
                        priority=issue_detail.priority,
                        status=issue_detail.status,
                    ),
                )
                if created:
                    result.issues_inserted += 1
                else:
                    result.issues_updated += 1

                changelog_entries = await self._jira_service.get_issue_changelog(
                    issue_key=issue_summary.key,
                    start_at=0,
                    max_results=self._settings.jira_sync_changelog_page_size,
                )
                filtered_history = self._filter_relevant_history(changelog_entries)
                result.history_fetched += len(filtered_history)
                inserted_count, skipped_count = SyncRepository.insert_issue_history_entries(
                    session=session,
                    entries=filtered_history,
                )
                result.history_inserted += inserted_count
                result.history_skipped += skipped_count

            # Keep metrics snapshots in sync with each successful Jira ingestion run.
            analytics_service = AnalyticsService()
            signal_service = SignalService()
            for release_id in version_name_to_release_id.values():
                analytics_service.recompute_release_metrics(session=session, release_id=release_id)
                signal_service.recompute_release_signal(session=session, release_id=release_id)

            session.commit()
        except JiraServiceError as exc:
            session.rollback()
            raise SyncServiceError(f"Jira sync failed: {exc}") from exc
        except ValueError as exc:
            session.rollback()
            raise SyncServiceError(f"Post-sync recompute failed: {exc}") from exc
        except SQLAlchemyError as exc:
            session.rollback()
            raise SyncServiceError(f"Database sync failed: {exc}") from exc

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
