from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Issue, IssueHistory, Release
from app.services.jira_types import JiraChangelogEntry, JiraIssueDetail, JiraVersion


def _parse_iso_date(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(f"{value}T00:00:00+00:00")
    except ValueError:
        return None


class SyncRepository:
    """Write-oriented persistence helpers for Jira sync."""

    @staticmethod
    def upsert_release(session: Session, version: JiraVersion) -> tuple[Release, bool]:
        existing = session.scalar(select(Release).where(Release.release_id == version.id))
        status = "released" if version.released else "unreleased"
        if existing is None:
            release = Release(
                release_id=version.id,
                name=version.name,
                project_key=version.project_key,
                description=version.description,
                status=status,
                start_date=_parse_iso_date(version.start_date),
                release_date=_parse_iso_date(version.release_date),
            )
            session.add(release)
            session.flush()
            return release, True

        existing.name = version.name
        existing.project_key = version.project_key
        existing.description = version.description
        existing.status = status
        existing.start_date = _parse_iso_date(version.start_date)
        existing.release_date = _parse_iso_date(version.release_date)
        session.flush()
        return existing, False

    @staticmethod
    def upsert_issue(
        session: Session,
        issue_detail: JiraIssueDetail,
        release_id: str | None,
        is_blocker: bool,
    ) -> tuple[Issue, bool]:
        existing = session.scalar(select(Issue).where(Issue.issue_key == issue_detail.key))
        if existing is None:
            issue = Issue(
                issue_key=issue_detail.key,
                summary=issue_detail.summary,
                issue_type=issue_detail.issue_type,
                status=issue_detail.status,
                priority=issue_detail.priority,
                assignee=issue_detail.assignee,
                release_id=release_id,
                is_blocker=is_blocker,
            )
            session.add(issue)
            session.flush()
            return issue, True

        existing.summary = issue_detail.summary
        existing.issue_type = issue_detail.issue_type
        existing.status = issue_detail.status
        existing.priority = issue_detail.priority
        existing.assignee = issue_detail.assignee
        existing.release_id = release_id
        existing.is_blocker = is_blocker
        session.flush()
        return existing, False

    @staticmethod
    def insert_issue_history_entries(
        session: Session,
        entries: list[JiraChangelogEntry],
    ) -> tuple[int, int]:
        inserted = 0
        skipped = 0
        for entry in entries:
            exists = session.scalar(
                select(IssueHistory.id).where(
                    IssueHistory.issue_key == entry.issue_key,
                    IssueHistory.field_name == entry.field_name,
                    IssueHistory.changed_at == entry.changed_at,
                    IssueHistory.old_value == entry.from_value,
                    IssueHistory.new_value == entry.to_value,
                )
            )
            if exists is not None:
                skipped += 1
                continue

            session.add(
                IssueHistory(
                    issue_key=entry.issue_key,
                    field_name=entry.field_name,
                    old_value=entry.from_value,
                    new_value=entry.to_value,
                    changed_at=entry.changed_at,
                )
            )
            inserted += 1

        session.flush()
        return inserted, skipped
