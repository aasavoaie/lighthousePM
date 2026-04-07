from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Issue


class IssueRepository:
    """Read-only queries for issue resources."""

    @staticmethod
    def get_issue_by_key(session: Session, issue_key: str) -> Issue | None:
        query = select(Issue).where(Issue.issue_key == issue_key)
        return session.scalar(query)
