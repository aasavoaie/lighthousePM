from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Issue, Release


class ReleaseRepository:
    """Read-only queries for release resources."""

    @staticmethod
    def list_releases(session: Session, skip: int, limit: int) -> tuple[list[Release], int]:
        total = session.scalar(select(func.count()).select_from(Release)) or 0
        query = select(Release).order_by(Release.release_id).offset(skip).limit(limit)
        releases = list(session.scalars(query).all())
        return releases, int(total)

    @staticmethod
    def get_release_by_id(session: Session, release_id: str) -> Release | None:
        query = select(Release).where(Release.release_id == release_id)
        return session.scalar(query)

    @staticmethod
    def list_release_ids(session: Session) -> list[str]:
        query = select(Release.release_id).order_by(Release.release_id)
        return list(session.scalars(query).all())

    @staticmethod
    def list_release_issues(
        session: Session, release_id: str, skip: int, limit: int
    ) -> tuple[list[Issue], int]:
        total_query = select(func.count()).select_from(Issue).where(Issue.release_id == release_id)
        total = session.scalar(total_query) or 0
        query = (
            select(Issue)
            .where(Issue.release_id == release_id)
            .order_by(Issue.issue_key)
            .offset(skip)
            .limit(limit)
        )
        issues = list(session.scalars(query).all())
        return issues, int(total)
