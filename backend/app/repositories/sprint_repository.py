from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Issue, IssueSprint, Sprint, SprintMetricSnapshot


class SprintRepository:
    """Read queries for sprint resources and sprint metric snapshots."""

    @staticmethod
    def list_sprints(
        session: Session,
        skip: int,
        limit: int,
        state: str | None = None,
    ) -> tuple[list[Sprint], int]:
        query = select(Sprint)
        count_query = select(func.count()).select_from(Sprint)
        if state is not None:
            normalized_state = state.casefold()
            query = query.where(func.lower(Sprint.state) == normalized_state)
            count_query = count_query.where(func.lower(Sprint.state) == normalized_state)

        total = session.scalar(count_query) or 0
        query = (
            query.order_by(Sprint.complete_date.desc().nullslast(), Sprint.end_date.desc().nullslast(), Sprint.name)
            .offset(skip)
            .limit(limit)
        )
        return list(session.scalars(query).all()), int(total)

    @staticmethod
    def get_sprint_by_id(session: Session, sprint_id: str) -> Sprint | None:
        return session.scalar(select(Sprint).where(Sprint.sprint_id == sprint_id))

    @staticmethod
    def get_current_sprint(session: Session) -> Sprint | None:
        query = (
            select(Sprint)
            .where(func.lower(Sprint.state) == "active")
            .order_by(Sprint.start_date.desc().nullslast(), Sprint.sprint_id)
            .limit(1)
        )
        return session.scalar(query)

    @staticmethod
    def list_sprint_ids(session: Session) -> list[str]:
        query = select(Sprint.sprint_id).order_by(Sprint.sprint_id)
        return list(session.scalars(query).all())

    @staticmethod
    def list_sprint_issues(
        session: Session, sprint_id: str, skip: int, limit: int
    ) -> tuple[list[Issue], int]:
        base = (
            select(Issue)
            .join(IssueSprint, IssueSprint.issue_key == Issue.issue_key)
            .where(IssueSprint.sprint_id == sprint_id)
        )
        total = session.scalar(
            select(func.count())
            .select_from(Issue)
            .join(IssueSprint, IssueSprint.issue_key == Issue.issue_key)
            .where(IssueSprint.sprint_id == sprint_id)
        ) or 0
        issues = list(session.scalars(base.order_by(Issue.issue_key).offset(skip).limit(limit)).all())
        return issues, int(total)

    @staticmethod
    def get_latest_metric_snapshot(session: Session, sprint_id: str) -> SprintMetricSnapshot | None:
        query = (
            select(SprintMetricSnapshot)
            .where(SprintMetricSnapshot.sprint_id == sprint_id)
            .order_by(SprintMetricSnapshot.snapshot_at.desc(), SprintMetricSnapshot.id.desc())
            .limit(1)
        )
        return session.scalar(query)
