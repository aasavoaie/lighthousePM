"""Insert deterministic sample data for local API testing."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.db.init import init_db
from app.db.session import SessionLocal
from app.models import Issue, IssueHistory, Release


def _seed_release(session) -> None:
    existing = session.scalar(select(Release).where(Release.release_id == "REL-DEMO-1"))
    if existing is not None:
        return

    now = datetime.now(UTC)
    session.add(
        Release(
            release_id="REL-DEMO-1",
            name="Demo Release 1",
            project_key="DEMO",
            description="Local sample release",
            status="active",
            start_date=now - timedelta(days=14),
            release_date=now + timedelta(days=7),
            created_at=now,
            updated_at=now,
        )
    )


def _seed_issues(session) -> None:
    issue_count = session.scalar(
        select(Issue.id).where(Issue.release_id == "REL-DEMO-1").limit(1)
    )
    if issue_count is not None:
        return

    now = datetime.now(UTC)
    issues = [
        Issue(
            issue_key="DEMO-1",
            summary="Implement dashboard widgets",
            issue_type="Story",
            status="In Progress",
            priority="Medium",
            assignee="alice",
            release_id="REL-DEMO-1",
            is_blocker=False,
            created_at=now - timedelta(days=10),
            updated_at=now,
        ),
        Issue(
            issue_key="DEMO-2",
            summary="Fix checkout bug",
            issue_type="Bug",
            status="In Progress",
            priority="High",
            assignee="bob",
            release_id="REL-DEMO-1",
            is_blocker=True,
            created_at=now - timedelta(days=8),
            updated_at=now,
        ),
        Issue(
            issue_key="DEMO-3",
            summary="Regression test coverage",
            issue_type="Task",
            status="Done",
            priority="Medium",
            assignee="carol",
            release_id="REL-DEMO-1",
            is_blocker=False,
            created_at=now - timedelta(days=12),
            updated_at=now,
        ),
    ]
    session.add_all(issues)


def _seed_history(session) -> None:
    existing = session.scalar(
        select(IssueHistory.id).where(IssueHistory.issue_key == "DEMO-3").limit(1)
    )
    if existing is not None:
        return

    now = datetime.now(UTC)
    entries = [
        IssueHistory(
            issue_key="DEMO-3",
            field_name="status",
            old_value="To Do",
            new_value="In Progress",
            changed_at=now - timedelta(days=9),
        ),
        IssueHistory(
            issue_key="DEMO-3",
            field_name="status",
            old_value="In Progress",
            new_value="Done",
            changed_at=now - timedelta(days=4),
        ),
        IssueHistory(
            issue_key="DEMO-3",
            field_name="fix version",
            old_value="Old Release",
            new_value="Demo Release 1",
            changed_at=now - timedelta(days=2),
        ),
    ]
    session.add_all(entries)


def main() -> None:
    init_db()
    with SessionLocal() as session:
        _seed_release(session)
        _seed_issues(session)
        _seed_history(session)
        session.commit()

    print("Seed data ready: REL-DEMO-1, DEMO-1..DEMO-3")


if __name__ == "__main__":
    main()
