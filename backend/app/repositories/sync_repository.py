from datetime import datetime

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models import Issue, IssueHistory, IssueSprint, Release, Sprint
from app.services.jira_types import JiraChangelogEntry, JiraIssueDetail, JiraSprintRef, JiraVersion


def _parse_iso_date(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(f"{value}T00:00:00+00:00")
    except ValueError:
        return None


def _parse_jira_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    normalized = value.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(normalized)
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
                story_points=issue_detail.story_points,
                release_id=release_id,
                is_blocker=is_blocker,
                jira_created_at=issue_detail.created,
                jira_updated_at=issue_detail.updated,
                jira_blocker_flag=issue_detail.blocker_flag,
            )
            session.add(issue)
            session.flush()
            return issue, True

        existing.summary = issue_detail.summary
        existing.issue_type = issue_detail.issue_type
        existing.status = issue_detail.status
        existing.priority = issue_detail.priority
        existing.assignee = issue_detail.assignee
        existing.story_points = issue_detail.story_points
        existing.release_id = release_id
        existing.is_blocker = is_blocker
        existing.jira_created_at = issue_detail.created
        existing.jira_updated_at = issue_detail.updated
        existing.jira_blocker_flag = issue_detail.blocker_flag
        session.flush()
        return existing, False

    @staticmethod
    def mark_issue_changelog_complete(session: Session, issue_key: str) -> None:
        issue = session.scalar(select(Issue).where(Issue.issue_key == issue_key))
        if issue is None:
            raise ValueError(f"Issue not found: {issue_key!r}")
        issue.jira_changelog_complete = True
        session.flush()

    @staticmethod
    def upsert_sprint(session: Session, sprint_ref: JiraSprintRef, project_key: str) -> tuple[Sprint, bool]:
        existing = session.scalar(select(Sprint).where(Sprint.sprint_id == sprint_ref.id))
        if existing is None:
            sprint = Sprint(
                sprint_id=sprint_ref.id,
                name=sprint_ref.name,
                state=sprint_ref.state,
                project_key=project_key,
                board_id=sprint_ref.board_id,
                start_date=_parse_jira_datetime(sprint_ref.start_date),
                end_date=_parse_jira_datetime(sprint_ref.end_date),
                complete_date=_parse_jira_datetime(sprint_ref.complete_date),
                goal=sprint_ref.goal,
            )
            session.add(sprint)
            session.flush()
            return sprint, True

        existing.name = sprint_ref.name
        existing.state = sprint_ref.state
        existing.project_key = project_key
        existing.board_id = sprint_ref.board_id
        existing.start_date = _parse_jira_datetime(sprint_ref.start_date)
        existing.end_date = _parse_jira_datetime(sprint_ref.end_date)
        existing.complete_date = _parse_jira_datetime(sprint_ref.complete_date)
        existing.goal = sprint_ref.goal
        session.flush()
        return existing, False

    @staticmethod
    def replace_issue_sprints(session: Session, issue_key: str, sprint_ids: list[str]) -> None:
        session.execute(delete(IssueSprint).where(IssueSprint.issue_key == issue_key))
        for sprint_id in dict.fromkeys(sprint_ids):
            session.add(IssueSprint(issue_key=issue_key, sprint_id=sprint_id))
        session.flush()

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
