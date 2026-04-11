import statistics
from datetime import UTC, datetime, timedelta
import logging

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import Issue, IssueHistory, MetricSnapshot, Release
from app.repositories.operational_status_repository import OperationalStatusRepository
from app.services.jira_field_mapper import JiraFieldMapper

logger = logging.getLogger(__name__)


class AnalyticsService:
    """Deterministic metrics computation for a single release.

    All methods are pure functions over stored Jira data — no Jira API calls.
    The caller owns the session transaction; recompute_release_metrics does not commit.

    Assumptions are documented in app/utils/constants.py and inline below.
    """

    def recompute_release_metrics(self, session: Session, release_id: str) -> MetricSnapshot:
        """Compute all six MVP metrics and persist a new MetricSnapshot row.

        The snapshot is added to *session* but not committed — the caller decides
        when to commit, enabling batching across multiple releases.
        """
        release = session.scalar(select(Release).where(Release.release_id == release_id))
        if release is None:
            raise ValueError(f"Release not found: {release_id!r}")

        logger.info("metrics_recompute_started release_id=%s", release_id)

        field_mapper = JiraFieldMapper(get_settings())

        snapshot = MetricSnapshot(
            release_id=release_id,
            snapshot_at=datetime.now(UTC),
            open_blockers=self._count_open_blockers(session, release_id, field_mapper),
            open_high_severity_bugs=self._count_open_high_severity_bugs(session, release_id, field_mapper),
            scope_completed_pct=self._compute_scope_completed_pct(session, release_id, field_mapper),
            scope_churn_7d_pct=self._compute_scope_churn_7d_pct(
                session,
                release_id,
                release.name,
                field_mapper,
            ),
            reopen_rate_pct=self._compute_reopen_rate_pct(session, release_id, field_mapper),
            median_cycle_time_days=self._compute_median_cycle_time_days(session, release_id, field_mapper),
        )
        session.add(snapshot)
        OperationalStatusRepository.mark_metrics_recomputed(session=session)
        logger.info(
            "metrics_recompute_completed release_id=%s open_blockers=%d open_high_severity_bugs=%d",
            release_id,
            snapshot.open_blockers,
            snapshot.open_high_severity_bugs,
        )
        return snapshot

    # ------------------------------------------------------------------
    # Private helpers — each computes exactly one metric
    # ------------------------------------------------------------------

    @staticmethod
    def _count_open_blockers(session: Session, release_id: str, field_mapper: JiraFieldMapper) -> int:
        """COUNT issues WHERE is_blocker AND status NOT IN done statuses."""
        result = session.scalar(
            select(func.count())
            .select_from(Issue)
            .where(
                Issue.release_id == release_id,
                Issue.is_blocker.is_(True),
                func.lower(Issue.status).not_in(field_mapper.done_statuses),
            )
        )
        return int(result or 0)

    @staticmethod
    def _count_open_high_severity_bugs(
        session: Session,
        release_id: str,
        field_mapper: JiraFieldMapper,
    ) -> int:
        """COUNT issues WHERE type='bug' AND priority in high-severity AND status NOT done."""
        result = session.scalar(
            select(func.count())
            .select_from(Issue)
            .where(
                Issue.release_id == release_id,
                func.lower(Issue.issue_type) == "bug",
                func.lower(Issue.priority).in_(field_mapper.high_severity_values),
                func.lower(Issue.status).not_in(field_mapper.done_statuses),
            )
        )
        return int(result or 0)

    @staticmethod
    def _compute_scope_completed_pct(
        session: Session,
        release_id: str,
        field_mapper: JiraFieldMapper,
    ) -> float:
        """100 * done_issues / total_issues. Returns 0.0 when release is empty.

        Assumption: scope is measured in issue count, not story points, because
        no story_points column exists in the MVP schema.
        """
        total = session.scalar(
            select(func.count()).select_from(Issue).where(Issue.release_id == release_id)
        ) or 0
        if total == 0:
            return 0.0
        done = session.scalar(
            select(func.count())
            .select_from(Issue)
            .where(
                Issue.release_id == release_id,
                func.lower(Issue.status).in_(field_mapper.done_statuses),
            )
        ) or 0
        return round(100.0 * done / total, 2)

    @staticmethod
    def _compute_scope_churn_7d_pct(
        session: Session,
        release_id: str,
        release_name: str,
        field_mapper: JiraFieldMapper,
    ) -> float:
        """100 * distinct churned issues / total issues in last 7 days.

        Churn = a 'fix version' field change in issue_history where the old or new value
        matches this release's name, within the last 7 days.

        Assumption: Jira changelog stores fix-version changes as field_name='fix version'
        (or 'fixversion') with old/new values equal to the version name string (case-insensitive).
        """
        total = session.scalar(
            select(func.count()).select_from(Issue).where(Issue.release_id == release_id)
        ) or 0
        if total == 0:
            return 0.0

        cutoff = datetime.now(UTC) - timedelta(days=7)
        release_name_lower = release_name.casefold()

        churned_keys = session.scalars(
            select(IssueHistory.issue_key)
            .where(
                func.lower(IssueHistory.field_name).in_(field_mapper.fix_version_changelog_fields),
                IssueHistory.changed_at >= cutoff,
                func.lower(IssueHistory.old_value).in_([release_name_lower])
                | func.lower(IssueHistory.new_value).in_([release_name_lower]),
            )
            .distinct()
        ).all()

        return round(100.0 * len(churned_keys) / total, 2)

    @staticmethod
    def _compute_reopen_rate_pct(
        session: Session,
        release_id: str,
        field_mapper: JiraFieldMapper,
    ) -> float:
        """100 * distinct reopened issues / total issues.

        Reopened = an issue in this release that has a status transition FROM a done
        status TO a non-done status (i.e. moved back into active work).

        Assumption: denominator is total issues in the release, not only those
        that were ever done. This is a conservative measure.
        """
        total = session.scalar(
            select(func.count()).select_from(Issue).where(Issue.release_id == release_id)
        ) or 0
        if total == 0:
            return 0.0

        # Subquery: issue_keys of all issues in this release
        release_issue_keys_subq = select(Issue.issue_key).where(Issue.release_id == release_id)

        reopened_keys = session.scalars(
            select(IssueHistory.issue_key)
            .where(
                IssueHistory.issue_key.in_(release_issue_keys_subq),
                IssueHistory.field_name == "status",
                func.lower(IssueHistory.old_value).in_(field_mapper.done_statuses),
                func.lower(IssueHistory.new_value).not_in(field_mapper.done_statuses),
            )
            .distinct()
        ).all()

        return round(100.0 * len(reopened_keys) / total, 2)

    @staticmethod
    def _compute_median_cycle_time_days(
        session: Session,
        release_id: str,
        field_mapper: JiraFieldMapper,
    ) -> float | None:
        """Median elapsed days from first 'in progress' to first 'done' transition.

        Only issues in this release that have BOTH transitions in issue_history are included.
        Issues that skipped 'in progress' (e.g. closed directly from 'to do') are excluded.

        Assumption: cycle time is measured per issue using the earliest qualifying status
        transition in issue_history. N+1 queries per release are used for clarity at MVP scale.
        """
        done_issues = session.scalars(
            select(Issue.issue_key).where(
                Issue.release_id == release_id,
                func.lower(Issue.status).in_(field_mapper.done_statuses),
            )
        ).all()

        cycle_days: list[float] = []

        for issue_key in done_issues:
            # Earliest transition INTO an in-progress status
            started_at = session.scalar(
                select(func.min(IssueHistory.changed_at)).where(
                    IssueHistory.issue_key == issue_key,
                    IssueHistory.field_name == "status",
                    func.lower(IssueHistory.new_value).in_(field_mapper.in_progress_statuses),
                )
            )
            # Earliest transition INTO a done status
            ended_at = session.scalar(
                select(func.min(IssueHistory.changed_at)).where(
                    IssueHistory.issue_key == issue_key,
                    IssueHistory.field_name == "status",
                    func.lower(IssueHistory.new_value).in_(field_mapper.done_statuses),
                )
            )

            if started_at is None or ended_at is None:
                continue
            if started_at >= ended_at:
                continue

            cycle_days.append((ended_at - started_at).total_seconds() / 86400)

        return round(statistics.median(cycle_days), 4) if cycle_days else None
