import logging
import math
import statistics
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import Issue, IssueHistory, IssueSprint, MetricSnapshot, Release, Sprint, SprintMetricSnapshot
from app.repositories.operational_status_repository import OperationalStatusRepository
from app.services.jira_field_mapper import JiraFieldMapper
from app.services.confidence_breakdown_service import ConfidenceBreakdownService
from app.services.metric_availability_service import (
    MetricAvailabilityService,
    UNAVAILABLE_REASON_RELEASE_EMPTY,
    UNAVAILABLE_REASON_SPRINT_EMPTY,
)
from app.services.signal_service import SignalService
from app.utils.constants import (
    DELIVERY_CONFIDENCE_STATUS_COMPUTED,
    DELIVERY_CONFIDENCE_STATUS_INCONCLUSIVE,
    DELIVERY_CONFIDENCE_STATUS_NOT_COMPUTED,
    DELIVERY_CONFIDENCE_STATUS_PARTIAL,
    MIN_STORY_POINT_COVERAGE_PCT,
    RULESET_VERSION,
    CYCLE_TIME_YELLOW_THRESHOLD_DAYS,
    CONFIDENCE_SCORE_GREEN_MIN,
    CONFIDENCE_SCORE_RED_MAX,
    CONFIDENCE_SCORE_YELLOW_MAX,
    CONFIDENCE_SCORE_YELLOW_MIN,
    HIGH_SEVERITY_BUGS_RED_THRESHOLD,
    HIGH_SEVERITY_BUGS_YELLOW_THRESHOLD,
    OPEN_BLOCKERS_RED_THRESHOLD,
    REOPEN_RATE_RED_THRESHOLD,
    REOPEN_RATE_YELLOW_THRESHOLD,
    SCOPE_CHURN_RED_THRESHOLD,
    SCOPE_CHURN_YELLOW_THRESHOLD,
)

logger = logging.getLogger(__name__)

DELIVERY_CONFIDENCE_WEIGHTS = {
    "progress_alignment": 0.4,
    "velocity_fit": 0.3,
    "blocker_penalty": 0.2,
    "scope_stability": 0.1,
}
HISTORICAL_VELOCITY_SPRINT_COUNT = 3


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

        open_blocker_issue_keys = self._list_open_blocker_issue_keys(session, release_id, field_mapper)
        open_high_severity_bug_issue_keys = self._list_open_high_severity_bug_issue_keys(
            session,
            release_id,
            field_mapper,
        )
        scope_churn_7d = self._compute_release_scope_churn_7d(
            session=session,
            release_id=release_id,
            project_key=release.project_key,
            release_name=release.name,
            field_mapper=field_mapper,
        )

        snapshot_at = datetime.now(UTC)
        ticket_count = int(
            session.scalar(
                select(func.count()).select_from(Issue).where(Issue.release_id == release_id)
            )
            or 0
        )
        scope_completed_pct = self._compute_scope_completed_pct(session, release_id, field_mapper)
        completed_tickets = self._count_completed_tickets(session, release_id, field_mapper)
        reopen_rate_pct = self._compute_reopen_rate_pct(session, release_id, field_mapper)
        median_cycle_time_days = self._compute_median_cycle_time_days(session, release_id, field_mapper)
        confidence_score = (
            SignalService._compute_release_confidence_score(
                open_blockers=len(open_blocker_issue_keys),
                open_high_severity_bugs=len(open_high_severity_bug_issue_keys),
                scope_churn_7d_pct=scope_churn_7d["scope_churn_7d_pct"],
                reopen_rate_pct=reopen_rate_pct,
                median_cycle_time_days=median_cycle_time_days,
            )
            if ticket_count > 0
            else None
        )
        snapshot = MetricSnapshot(
            release_id=release_id,
            snapshot_at=snapshot_at,
            ruleset_version=RULESET_VERSION,
            confidence_score=confidence_score,
            confidence_status="COMPUTED" if confidence_score is not None else "NOT_COMPUTED",
            open_blockers=len(open_blocker_issue_keys),
            open_high_severity_bugs=len(open_high_severity_bug_issue_keys),
            open_blocker_issue_keys=open_blocker_issue_keys,
            open_high_severity_bug_issue_keys=open_high_severity_bug_issue_keys,
            scope_completed_pct=scope_completed_pct,
            completed_tickets=completed_tickets,
            scope_churn_7d_pct=scope_churn_7d["scope_churn_7d_pct"],
            scope_added_7d_count=scope_churn_7d["scope_added_7d_count"],
            scope_removed_7d_count=scope_churn_7d["scope_removed_7d_count"],
            reopen_rate_pct=reopen_rate_pct,
            median_cycle_time_days=median_cycle_time_days,
        )
        snapshot.calculation_provenance = self._release_calculation_provenance(
            session=session,
            release_id=release_id,
            snapshot=snapshot,
            field_mapper=field_mapper,
            ticket_count=ticket_count,
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

    def recompute_sprint_metrics(self, session: Session, sprint_id: str) -> SprintMetricSnapshot:
        """Compute sprint metrics and persist a new SprintMetricSnapshot row.

        Sprint scope is the explicit issue_sprints membership stored from Jira.
        Rollover count is only populated for closed sprints and means sprint
        issues that are not currently in a configured done status.
        """
        sprint = session.scalar(select(Sprint).where(Sprint.sprint_id == sprint_id))
        if sprint is None:
            raise ValueError(f"Sprint not found: {sprint_id!r}")

        logger.info("sprint_metrics_recompute_started sprint_id=%s", sprint_id)
        field_mapper = JiraFieldMapper(get_settings())

        open_blocker_issue_keys = self._list_sprint_open_blocker_issue_keys(session, sprint_id, field_mapper)
        open_high_severity_bug_issue_keys = self._list_sprint_open_high_severity_bug_issue_keys(
            session,
            sprint_id,
            field_mapper,
        )
        snapshot_at = datetime.now(UTC)
        bugs_created_during_sprint = self._compute_bugs_created_during_sprint(
            session=session,
            sprint=sprint,
            snapshot_at=snapshot_at,
        )
        delivery_confidence = self._compute_delivery_confidence(
            session=session,
            sprint=sprint,
            snapshot_at=snapshot_at,
            field_mapper=field_mapper,
            open_blockers=len(open_blocker_issue_keys),
        )

        snapshot = SprintMetricSnapshot(
            sprint_id=sprint_id,
            snapshot_at=snapshot_at,
            ruleset_version=RULESET_VERSION,
            committed_scope=self._count_sprint_issues(session, sprint_id),
            completed_scope_pct=self._compute_sprint_completed_scope_pct(session, sprint_id, field_mapper),
            open_blockers=len(open_blocker_issue_keys),
            open_high_severity_bugs=len(open_high_severity_bug_issue_keys),
            bugs_created_during_sprint=len(bugs_created_during_sprint["issue_keys"]),
            open_blocker_issue_keys=open_blocker_issue_keys,
            open_high_severity_bug_issue_keys=open_high_severity_bug_issue_keys,
            bugs_created_during_sprint_issue_keys=bugs_created_during_sprint["issue_keys"],
            bugs_created_during_sprint_status=bugs_created_during_sprint["status"],
            bugs_created_during_sprint_missing_created_at_issue_keys=bugs_created_during_sprint[
                "missing_created_at_issue_keys"
            ],
            in_progress_count=self._count_sprint_in_progress(session, sprint_id, field_mapper),
            not_started_count=self._count_sprint_not_started(session, sprint_id, field_mapper),
            rollover_count=self._count_sprint_rollover(session, sprint_id, sprint.state, field_mapper),
            median_cycle_time_days=self._compute_sprint_median_cycle_time_days(session, sprint_id, field_mapper),
            reopen_rate_pct=self._compute_sprint_reopen_rate_pct(session, sprint_id, field_mapper),
            delivery_confidence_score=delivery_confidence["score"],
            delivery_confidence_components=delivery_confidence["components"],
            delivery_confidence_inputs=delivery_confidence["inputs"],
            story_point_total_count=delivery_confidence["coverage"]["total_ticket_count"],
            story_point_pointed_count=delivery_confidence["coverage"]["pointed_ticket_count"],
            story_point_unpointed_count=delivery_confidence["coverage"]["unpointed_ticket_count"],
            story_point_coverage_pct=delivery_confidence["coverage"]["coverage_pct"],
            story_point_unpointed_issue_keys=delivery_confidence["coverage"]["unpointed_issue_keys"],
            delivery_confidence_status=delivery_confidence["status"],
            delivery_confidence_explanations=delivery_confidence["explanations"],
        )
        snapshot.calculation_provenance = self._sprint_calculation_provenance(
            session=session,
            sprint_id=sprint_id,
            snapshot=snapshot,
            field_mapper=field_mapper,
        )
        session.add(snapshot)
        OperationalStatusRepository.mark_metrics_recomputed(session=session)
        logger.info(
            "sprint_metrics_recompute_completed sprint_id=%s committed_scope=%d completed_scope_pct=%.2f",
            sprint_id,
            snapshot.committed_scope,
            snapshot.completed_scope_pct,
        )
        return snapshot

    @staticmethod
    def _classification_provenance(field_mapper: JiraFieldMapper) -> dict[str, object]:
        return {
            "done_statuses": sorted(field_mapper.done_statuses),
            "in_progress_statuses": sorted(field_mapper.in_progress_statuses),
            "high_severity_values": sorted(field_mapper.high_severity_values),
            "severity_field": field_mapper.mapping.severity_field,
            "story_points_field": field_mapper.mapping.story_points_field,
            "release_field": field_mapper.mapping.release_field,
            "sprint_field": field_mapper.mapping.sprint_field,
            "blocker_field": field_mapper.mapping.blocker_field,
            "blocker_true_values": sorted(field_mapper.mapping.blocker_true_values),
        }

    @staticmethod
    def _history_completeness_evidence(
        session: Session,
        issue_keys_query,
    ) -> dict[str, object]:
        issues = list(
            session.scalars(
                select(Issue).where(Issue.issue_key.in_(issue_keys_query)).order_by(Issue.issue_key)
            ).all()
        )
        complete_keys = [issue.issue_key for issue in issues if issue.jira_changelog_complete]
        incomplete_keys = [issue.issue_key for issue in issues if not issue.jira_changelog_complete]
        return {
            "complete_issue_keys": complete_keys,
            "incomplete_issue_keys": incomplete_keys,
            "complete_count": len(complete_keys),
            "incomplete_count": len(incomplete_keys),
        }

    @staticmethod
    def _release_calculation_provenance(
        session: Session,
        release_id: str,
        snapshot: MetricSnapshot,
        field_mapper: JiraFieldMapper,
        ticket_count: int,
    ) -> dict[str, object]:
        from app.services.driver_analysis_service import DriverAnalysisService

        readiness = (
            SignalService._build_release_readiness_details(
                signal=None,
                open_blockers=snapshot.open_blockers,
                open_high_severity_bugs=snapshot.open_high_severity_bugs,
                scope_churn_7d_pct=snapshot.scope_churn_7d_pct,
                reopen_rate_pct=snapshot.reopen_rate_pct,
                median_cycle_time_days=snapshot.median_cycle_time_days,
            )
            if ticket_count > 0
            else {}
        )
        availability = MetricAvailabilityService.build_release_availability(
            session=session,
            release_id=release_id,
            field_mapper=field_mapper,
        )
        computation_status, unavailable_reason = MetricAvailabilityService.computation_state(
            availability,
            is_computed=True,
            empty_scope_reason=UNAVAILABLE_REASON_RELEASE_EMPTY,
        )
        return {
            "source_calculated_at": snapshot.snapshot_at.isoformat(),
            "thresholds": {
                "open_blockers_red": OPEN_BLOCKERS_RED_THRESHOLD,
                "open_high_severity_bugs_red": HIGH_SEVERITY_BUGS_RED_THRESHOLD,
                "open_high_severity_bugs_yellow": HIGH_SEVERITY_BUGS_YELLOW_THRESHOLD,
                "scope_churn_7d_pct_red": SCOPE_CHURN_RED_THRESHOLD * 100,
                "scope_churn_7d_pct_yellow": SCOPE_CHURN_YELLOW_THRESHOLD * 100,
                "reopen_rate_pct_red": REOPEN_RATE_RED_THRESHOLD * 100,
                "reopen_rate_pct_yellow": REOPEN_RATE_YELLOW_THRESHOLD * 100,
                "median_cycle_time_days_yellow": CYCLE_TIME_YELLOW_THRESHOLD_DAYS,
                "confidence_score_red_max": CONFIDENCE_SCORE_RED_MAX,
                "confidence_score_yellow_min": CONFIDENCE_SCORE_YELLOW_MIN,
                "confidence_score_yellow_max": CONFIDENCE_SCORE_YELLOW_MAX,
                "confidence_score_green_min": CONFIDENCE_SCORE_GREEN_MIN,
            },
            "weights": dict(SignalService.RISK_WEIGHTS),
            "classification": AnalyticsService._classification_provenance(field_mapper),
            "availability": availability.model_dump(),
            "computation_status": computation_status,
            "unavailable_reason": unavailable_reason,
            "story_point_coverage": None,
            "history_completeness": AnalyticsService._history_completeness_evidence(
                session,
                select(Issue.issue_key).where(Issue.release_id == release_id),
            ),
            "component_inputs": {
                "open_blockers": snapshot.open_blockers,
                "open_high_severity_bugs": snapshot.open_high_severity_bugs,
                "scope_churn_7d_pct": snapshot.scope_churn_7d_pct,
                "reopen_rate_pct": snapshot.reopen_rate_pct,
                "median_cycle_time_days": snapshot.median_cycle_time_days,
            },
            "component_outputs": {
                "risk_points": SignalService._compute_release_risk_points(
                    open_blockers=snapshot.open_blockers,
                    open_high_severity_bugs=snapshot.open_high_severity_bugs,
                    scope_churn_7d_pct=snapshot.scope_churn_7d_pct,
                    reopen_rate_pct=snapshot.reopen_rate_pct,
                    median_cycle_time_days=snapshot.median_cycle_time_days,
                ),
                "confidence_breakdown": (
                    ConfidenceBreakdownService.build_release_breakdown(snapshot).model_dump()
                    if snapshot.confidence_score is not None
                    else None
                ),
                "biggest_driver": (
                    DriverAnalysisService.build_release_driver(snapshot).model_dump()
                    if snapshot.confidence_score is not None
                    else None
                ),
                "release_gates": readiness.get("release_gates", []),
                "readiness_pct": (
                    round(
                        100.0
                        * sum(1 for gate in readiness.get("release_gates", []) if gate.get("passed") is True)
                        / len(readiness.get("release_gates", [])),
                        2,
                    )
                    if readiness.get("release_gates")
                    else None
                ),
            },
            "issue_key_evidence": {
                "open_blockers": snapshot.open_blocker_issue_keys,
                "open_high_severity_bugs": snapshot.open_high_severity_bug_issue_keys,
            },
        }

    @staticmethod
    def _sprint_calculation_provenance(
        session: Session,
        sprint_id: str,
        snapshot: SprintMetricSnapshot,
        field_mapper: JiraFieldMapper,
    ) -> dict[str, object]:
        from app.services.driver_analysis_service import DriverAnalysisService

        has_confidence = (
            snapshot.delivery_confidence_score is not None
            and snapshot.delivery_confidence_components is not None
        )
        availability = MetricAvailabilityService.build_sprint_availability(
            session=session,
            sprint_id=sprint_id,
            field_mapper=field_mapper,
        )
        computation_status, unavailable_reason = MetricAvailabilityService.computation_state(
            availability,
            is_computed=True,
            empty_scope_reason=UNAVAILABLE_REASON_SPRINT_EMPTY,
        )
        return {
            "source_calculated_at": snapshot.snapshot_at.isoformat(),
            "thresholds": {"minimum_story_point_coverage_pct": MIN_STORY_POINT_COVERAGE_PCT},
            "weights": dict(DELIVERY_CONFIDENCE_WEIGHTS),
            "classification": AnalyticsService._classification_provenance(field_mapper),
            "availability": availability.model_dump(),
            "computation_status": computation_status,
            "unavailable_reason": unavailable_reason,
            "story_point_coverage": {
                "total_ticket_count": snapshot.story_point_total_count,
                "pointed_ticket_count": snapshot.story_point_pointed_count,
                "unpointed_ticket_count": snapshot.story_point_unpointed_count,
                "coverage_pct": snapshot.story_point_coverage_pct,
                "unpointed_issue_keys": snapshot.story_point_unpointed_issue_keys,
            },
            "history_completeness": AnalyticsService._history_completeness_evidence(
                session,
                AnalyticsService._sprint_issue_keys_subquery(sprint_id),
            ),
            "component_inputs": snapshot.delivery_confidence_inputs,
            "component_outputs": {
                "components": snapshot.delivery_confidence_components,
                "confidence_breakdown": (
                    ConfidenceBreakdownService.build_sprint_breakdown(
                        score=float(snapshot.delivery_confidence_score),
                        components=snapshot.delivery_confidence_components or {},
                        inputs=snapshot.delivery_confidence_inputs,
                    ).model_dump()
                    if has_confidence
                    else None
                ),
                "biggest_driver": (
                    DriverAnalysisService.build_sprint_driver(
                        score=float(snapshot.delivery_confidence_score),
                        components=snapshot.delivery_confidence_components or {},
                    ).model_dump()
                    if has_confidence
                    else None
                ),
            },
            "issue_key_evidence": {
                "open_blockers": snapshot.open_blocker_issue_keys,
                "open_high_severity_bugs": snapshot.open_high_severity_bug_issue_keys,
                "bugs_created_during_sprint": snapshot.bugs_created_during_sprint_issue_keys,
                "bugs_missing_jira_created_at": (
                    snapshot.bugs_created_during_sprint_missing_created_at_issue_keys
                ),
            },
        }

    def compute_sprint_initial_scope_flags(
        self,
        session: Session,
        sprint: Sprint,
        issue_keys: list[str],
        snapshot_at: datetime,
    ) -> dict[str, bool]:
        """Return whether each current sprint issue was in scope at sprint start.

        The calculation starts from current sprint membership and reverses sprint
        changelog transitions after the sprint start.
        """
        flags = {issue_key: True for issue_key in issue_keys}
        if not issue_keys:
            return flags

        field_mapper = JiraFieldMapper(get_settings())
        start_at = _coerce_utc(sprint.start_date)
        if start_at is None:
            return flags

        snapshot_at = _coerce_utc(snapshot_at) or snapshot_at
        end_at = _coerce_utc(sprint.end_date)
        upper_bound = min(snapshot_at, end_at) if end_at is not None else snapshot_at
        if upper_bound <= start_at:
            return flags

        entries = session.scalars(
            select(IssueHistory)
            .where(
                IssueHistory.issue_key.in_(issue_keys),
                func.lower(IssueHistory.field_name).in_(field_mapper.sprint_changelog_fields),
                IssueHistory.changed_at > start_at,
                IssueHistory.changed_at <= upper_bound,
            )
            .order_by(IssueHistory.issue_key, IssueHistory.changed_at.desc(), IssueHistory.id.desc())
        ).all()

        for entry in entries:
            old_references_sprint = _history_value_references_sprint(entry.old_value, sprint)
            new_references_sprint = _history_value_references_sprint(entry.new_value, sprint)
            if old_references_sprint != new_references_sprint:
                flags[entry.issue_key] = old_references_sprint

        return flags

    # ------------------------------------------------------------------
    # Private helpers — each computes exactly one metric
    # ------------------------------------------------------------------

    @staticmethod
    def _count_open_blockers(session: Session, release_id: str, field_mapper: JiraFieldMapper) -> int:
        """COUNT issues WHERE is_blocker AND status NOT IN done statuses."""
        return len(AnalyticsService._list_open_blocker_issue_keys(session, release_id, field_mapper))

    @staticmethod
    def _list_open_blocker_issue_keys(
        session: Session,
        release_id: str,
        field_mapper: JiraFieldMapper,
    ) -> list[str]:
        """Sorted issue keys WHERE is_blocker AND status NOT IN done statuses."""
        return list(
            session.scalars(
                select(Issue.issue_key)
                .select_from(Issue)
                .where(
                    Issue.release_id == release_id,
                    Issue.is_blocker.is_(True),
                    func.lower(Issue.status).not_in(field_mapper.done_statuses),
                )
                .order_by(Issue.issue_key)
            ).all()
        )

    @staticmethod
    def _list_open_high_severity_bug_issue_keys(
        session: Session,
        release_id: str,
        field_mapper: JiraFieldMapper,
    ) -> list[str]:
        """Sorted issue keys WHERE type='bug' AND priority in high-severity AND status NOT done."""
        return list(
            session.scalars(
                select(Issue.issue_key)
                .select_from(Issue)
                .where(
                    Issue.release_id == release_id,
                    func.lower(Issue.issue_type) == "bug",
                    func.lower(Issue.priority).in_(field_mapper.high_severity_values),
                    func.lower(Issue.status).not_in(field_mapper.done_statuses),
                )
                .order_by(Issue.issue_key)
            ).all()
        )

    @staticmethod
    def _count_open_high_severity_bugs(
        session: Session,
        release_id: str,
        field_mapper: JiraFieldMapper,
    ) -> int:
        """COUNT issues WHERE type='bug' AND priority in high-severity AND status NOT done."""
        return len(AnalyticsService._list_open_high_severity_bug_issue_keys(session, release_id, field_mapper))

    @staticmethod
    def _compute_scope_completed_pct(
        session: Session,
        release_id: str,
        field_mapper: JiraFieldMapper,
    ) -> float:
        """100 * done_issues / total_issues. Returns 0.0 when release is empty.

        Assumption: release scope remains measured in issue count for API
        compatibility; sprint delivery confidence uses story points separately.
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
    def _count_completed_tickets(
        session: Session,
        release_id: str,
        field_mapper: JiraFieldMapper,
    ) -> int:
        """COUNT release issues currently in a configured done status."""
        return session.scalar(
            select(func.count())
            .select_from(Issue)
            .where(
                Issue.release_id == release_id,
                func.lower(Issue.status).in_(field_mapper.done_statuses),
            )
        ) or 0

    @staticmethod
    def _compute_scope_churn_7d_pct(
        session: Session,
        release_id: str,
        project_key: str,
        release_name: str,
        field_mapper: JiraFieldMapper,
    ) -> float:
        return float(
            AnalyticsService._compute_release_scope_churn_7d(
                session=session,
                release_id=release_id,
                project_key=project_key,
                release_name=release_name,
                field_mapper=field_mapper,
            )["scope_churn_7d_pct"]
        )

    @staticmethod
    def _compute_release_scope_churn_7d(
        session: Session,
        release_id: str,
        project_key: str,
        release_name: str,
        field_mapper: JiraFieldMapper,
    ) -> dict[str, int | float]:
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
            return {
                "scope_churn_7d_pct": 0.0,
                "scope_added_7d_count": 0,
                "scope_removed_7d_count": 0,
            }

        cutoff = datetime.now(UTC) - timedelta(days=7)
        release_name_lower = release_name.casefold()

        entries = session.scalars(
            select(IssueHistory)
            .where(
                IssueHistory.issue_key.in_(
                    select(Issue.issue_key).where(
                        or_(
                            Issue.release_id == release_id,
                            _issue_key_matches_project(Issue.issue_key, project_key),
                        )
                    )
                ),
                func.lower(IssueHistory.field_name).in_(field_mapper.fix_version_changelog_fields),
                IssueHistory.changed_at >= cutoff,
                func.lower(IssueHistory.old_value).in_([release_name_lower])
                | func.lower(IssueHistory.new_value).in_([release_name_lower]),
            )
        ).all()

        churned_keys: set[str] = set()
        added_keys: set[str] = set()
        removed_keys: set[str] = set()
        for entry in entries:
            old_references_release = (entry.old_value or "").casefold() == release_name_lower
            new_references_release = (entry.new_value or "").casefold() == release_name_lower
            churned_keys.add(entry.issue_key)
            if not old_references_release and new_references_release:
                added_keys.add(entry.issue_key)
            elif old_references_release and not new_references_release:
                removed_keys.add(entry.issue_key)

        return {
            "scope_churn_7d_pct": round(100.0 * len(churned_keys) / total, 2),
            "scope_added_7d_count": len(added_keys),
            "scope_removed_7d_count": len(removed_keys),
        }

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

    # ------------------------------------------------------------------
    # Sprint metrics
    # ------------------------------------------------------------------

    @staticmethod
    def _sprint_issue_keys_subquery(sprint_id: str):
        return select(IssueSprint.issue_key).where(IssueSprint.sprint_id == sprint_id)

    @staticmethod
    def _count_sprint_issues(session: Session, sprint_id: str) -> int:
        total = session.scalar(
            select(func.count()).select_from(IssueSprint).where(IssueSprint.sprint_id == sprint_id)
        )
        return int(total or 0)

    @staticmethod
    def _compute_sprint_completed_scope_pct(
        session: Session,
        sprint_id: str,
        field_mapper: JiraFieldMapper,
    ) -> float:
        total = AnalyticsService._count_sprint_issues(session, sprint_id)
        if total == 0:
            return 0.0
        done = session.scalar(
            select(func.count())
            .select_from(Issue)
            .where(
                Issue.issue_key.in_(AnalyticsService._sprint_issue_keys_subquery(sprint_id)),
                func.lower(Issue.status).in_(field_mapper.done_statuses),
            )
        ) or 0
        return round(100.0 * done / total, 2)

    @staticmethod
    def _count_sprint_open_blockers(
        session: Session,
        sprint_id: str,
        field_mapper: JiraFieldMapper,
    ) -> int:
        return len(AnalyticsService._list_sprint_open_blocker_issue_keys(session, sprint_id, field_mapper))

    @staticmethod
    def _list_sprint_open_blocker_issue_keys(
        session: Session,
        sprint_id: str,
        field_mapper: JiraFieldMapper,
    ) -> list[str]:
        return list(
            session.scalars(
                select(Issue.issue_key)
                .select_from(Issue)
                .where(
                    Issue.issue_key.in_(AnalyticsService._sprint_issue_keys_subquery(sprint_id)),
                    Issue.is_blocker.is_(True),
                    func.lower(Issue.status).not_in(field_mapper.done_statuses),
                )
                .order_by(Issue.issue_key)
            ).all()
        )

    @staticmethod
    def _count_sprint_open_high_severity_bugs(
        session: Session,
        sprint_id: str,
        field_mapper: JiraFieldMapper,
    ) -> int:
        return len(AnalyticsService._list_sprint_open_high_severity_bug_issue_keys(session, sprint_id, field_mapper))

    @staticmethod
    def _list_sprint_open_high_severity_bug_issue_keys(
        session: Session,
        sprint_id: str,
        field_mapper: JiraFieldMapper,
    ) -> list[str]:
        return list(
            session.scalars(
                select(Issue.issue_key)
                .select_from(Issue)
                .where(
                    Issue.issue_key.in_(AnalyticsService._sprint_issue_keys_subquery(sprint_id)),
                    func.lower(Issue.issue_type) == "bug",
                    func.lower(Issue.priority).in_(field_mapper.high_severity_values),
                    func.lower(Issue.status).not_in(field_mapper.done_statuses),
                )
                .order_by(Issue.issue_key)
            ).all()
        )

    @staticmethod
    def _compute_bugs_created_during_sprint(
        session: Session,
        sprint: Sprint,
        snapshot_at: datetime,
    ) -> dict[str, object]:
        """Sorted sprint bug keys where issue creation falls inside the sprint window.

        The window starts at sprint.start_date. It ends at complete_date for closed
        sprints when present, otherwise end_date, capped at snapshot_at for active
        sprints whose configured end date is in the future.
        """
        start_at = _coerce_utc(sprint.start_date)
        snapshot_at = _coerce_utc(snapshot_at)
        if start_at is None or snapshot_at is None:
            return {
                "status": "NOT_COMPUTED",
                "issue_keys": [],
                "missing_created_at_issue_keys": [],
            }

        if sprint.state.casefold() == "closed":
            upper_bound = (
                _coerce_utc(sprint.complete_date)
                or _coerce_utc(sprint.end_date)
                or snapshot_at
            )
        else:
            configured_end_at = _coerce_utc(sprint.end_date)
            upper_bound = min(configured_end_at, snapshot_at) if configured_end_at is not None else snapshot_at
        if upper_bound < start_at:
            return {
                "status": "COMPUTED",
                "issue_keys": [],
                "missing_created_at_issue_keys": [],
            }

        bugs = list(
            session.scalars(
                select(Issue)
                .where(
                    Issue.issue_key.in_(AnalyticsService._sprint_issue_keys_subquery(sprint.sprint_id)),
                    func.lower(Issue.issue_type) == "bug",
                )
                .order_by(Issue.issue_key)
            ).all()
        )
        missing_created_at_issue_keys = sorted(
            issue.issue_key for issue in bugs if issue.jira_created_at is None
        )
        issue_keys = sorted(
            issue.issue_key
            for issue in bugs
            if issue.jira_created_at is not None
            and start_at <= (_coerce_utc(issue.jira_created_at) or start_at) <= upper_bound
        )
        return {
            "status": "PARTIAL" if missing_created_at_issue_keys else "COMPUTED",
            "issue_keys": issue_keys,
            "missing_created_at_issue_keys": missing_created_at_issue_keys,
        }

    @staticmethod
    def _count_sprint_in_progress(
        session: Session,
        sprint_id: str,
        field_mapper: JiraFieldMapper,
    ) -> int:
        result = session.scalar(
            select(func.count())
            .select_from(Issue)
            .where(
                Issue.issue_key.in_(AnalyticsService._sprint_issue_keys_subquery(sprint_id)),
                func.lower(Issue.status).in_(field_mapper.in_progress_statuses),
            )
        )
        return int(result or 0)

    @staticmethod
    def _count_sprint_not_started(
        session: Session,
        sprint_id: str,
        field_mapper: JiraFieldMapper,
    ) -> int:
        result = session.scalar(
            select(func.count())
            .select_from(Issue)
            .where(
                Issue.issue_key.in_(AnalyticsService._sprint_issue_keys_subquery(sprint_id)),
                func.lower(Issue.status).not_in(field_mapper.done_statuses),
                func.lower(Issue.status).not_in(field_mapper.in_progress_statuses),
            )
        )
        return int(result or 0)

    @staticmethod
    def _count_sprint_rollover(
        session: Session,
        sprint_id: str,
        sprint_state: str,
        field_mapper: JiraFieldMapper,
    ) -> int:
        if sprint_state.casefold() != "closed":
            return 0
        result = session.scalar(
            select(func.count())
            .select_from(Issue)
            .where(
                Issue.issue_key.in_(AnalyticsService._sprint_issue_keys_subquery(sprint_id)),
                func.lower(Issue.status).not_in(field_mapper.done_statuses),
            )
        )
        return int(result or 0)

    @staticmethod
    def _compute_sprint_reopen_rate_pct(
        session: Session,
        sprint_id: str,
        field_mapper: JiraFieldMapper,
    ) -> float:
        total = AnalyticsService._count_sprint_issues(session, sprint_id)
        if total == 0:
            return 0.0

        reopened_keys = session.scalars(
            select(IssueHistory.issue_key)
            .where(
                IssueHistory.issue_key.in_(AnalyticsService._sprint_issue_keys_subquery(sprint_id)),
                IssueHistory.field_name == "status",
                func.lower(IssueHistory.old_value).in_(field_mapper.done_statuses),
                func.lower(IssueHistory.new_value).not_in(field_mapper.done_statuses),
            )
            .distinct()
        ).all()

        return round(100.0 * len(reopened_keys) / total, 2)

    @staticmethod
    def _compute_sprint_median_cycle_time_days(
        session: Session,
        sprint_id: str,
        field_mapper: JiraFieldMapper,
    ) -> float | None:
        done_issues = session.scalars(
            select(Issue.issue_key).where(
                Issue.issue_key.in_(AnalyticsService._sprint_issue_keys_subquery(sprint_id)),
                func.lower(Issue.status).in_(field_mapper.done_statuses),
            )
        ).all()

        cycle_days: list[float] = []
        for issue_key in done_issues:
            started_at = session.scalar(
                select(func.min(IssueHistory.changed_at)).where(
                    IssueHistory.issue_key == issue_key,
                    IssueHistory.field_name == "status",
                    func.lower(IssueHistory.new_value).in_(field_mapper.in_progress_statuses),
                )
            )
            ended_at = session.scalar(
                select(func.min(IssueHistory.changed_at)).where(
                    IssueHistory.issue_key == issue_key,
                    IssueHistory.field_name == "status",
                    func.lower(IssueHistory.new_value).in_(field_mapper.done_statuses),
                )
            )
            if started_at is None or ended_at is None or started_at >= ended_at:
                continue
            cycle_days.append((ended_at - started_at).total_seconds() / 86400)

        return round(statistics.median(cycle_days), 4) if cycle_days else None

    @staticmethod
    def _compute_delivery_confidence(
        session: Session,
        sprint: Sprint,
        snapshot_at: datetime,
        field_mapper: JiraFieldMapper,
        open_blockers: int,
    ) -> dict[str, object]:
        sprint_issues = AnalyticsService._list_sprint_issues(session, sprint.sprint_id)
        committed_issue_count = len(sprint_issues)
        coverage = _story_point_coverage(sprint_issues)
        if committed_issue_count == 0:
            return {
                "status": DELIVERY_CONFIDENCE_STATUS_NOT_COMPUTED,
                "score": None,
                "components": None,
                "inputs": None,
                "coverage": coverage,
                "explanations": [
                    "Delivery confidence is not computed because the sprint has no tickets to evaluate."
                ],
            }
        if coverage["coverage_pct"] < MIN_STORY_POINT_COVERAGE_PCT:
            return {
                "status": DELIVERY_CONFIDENCE_STATUS_INCONCLUSIVE,
                "score": None,
                "components": None,
                "inputs": None,
                "coverage": coverage,
                "explanations": [
                    "Delivery confidence is inconclusive because fewer than 50% of the sprint tickets have story "
                    "points. At least 50% of the tickets inside the sprint must have story points to calculate "
                    "delivery confidence. Ideally, all tickets should have story points."
                ],
            }

        pointed_issues = [issue for issue in sprint_issues if _valid_story_points(issue.story_points) is not None]
        status = (
            DELIVERY_CONFIDENCE_STATUS_COMPUTED
            if coverage["coverage_pct"] == 100.0
            else DELIVERY_CONFIDENCE_STATUS_PARTIAL
        )
        explanations: list[str] = []
        if status == DELIVERY_CONFIDENCE_STATUS_PARTIAL:
            explanations.extend(
                [
                    (
                        "Delivery confidence is partial because "
                        f"{coverage['pointed_ticket_count']} of {coverage['total_ticket_count']} sprint tickets "
                        "have story points. Point-based calculations use tickets with available story points, "
                        "while blocker and scope calculations use the complete sprint scope."
                    ),
                    (
                        "When all sprint tickets have story points, delivery confidence uses the complete sprint "
                        "scope and returns the accurate value for the documented model. The PARTIAL label and "
                        "these remarks are then removed."
                    ),
                ]
            )

        committed_effective_points = sum(_story_points(issue) for issue in pointed_issues)
        completed_effective_points = sum(
            _story_points(issue)
            for issue in pointed_issues
            if field_mapper.is_done_status(issue.status)
        )
        remaining_effective_points = max(committed_effective_points - completed_effective_points, 0.0)
        # For confidence scoring, no committed work means there is no incomplete work.
        completed_scope_pct = (
            100.0
            if committed_effective_points == 0
            else 100.0 * completed_effective_points / committed_effective_points
        )

        time_elapsed_pct = _compute_time_elapsed_pct(sprint=sprint, snapshot_at=snapshot_at)
        progress_alignment = _score_progress_alignment(
            completed_scope_pct=completed_scope_pct,
            time_elapsed_pct=time_elapsed_pct,
        )

        baseline_sprints = AnalyticsService._list_velocity_baseline_sprints(session=session, sprint=sprint)
        baseline_evidence = []
        for baseline in baseline_sprints:
            baseline_issues = AnalyticsService._list_sprint_issues(session, baseline.sprint_id)
            baseline_coverage = _story_point_coverage(baseline_issues)
            completed_points = AnalyticsService._compute_completed_effective_points_for_sprint(
                session=session,
                sprint_id=baseline.sprint_id,
                field_mapper=field_mapper,
            )
            baseline_evidence.append(
                {
                    "sprint_id": baseline.sprint_id,
                    "coverage_pct": baseline_coverage["coverage_pct"],
                    "status": (
                        DELIVERY_CONFIDENCE_STATUS_COMPUTED
                        if baseline_coverage["coverage_pct"] == 100.0
                        else DELIVERY_CONFIDENCE_STATUS_PARTIAL
                    ),
                    "completed_points": round(completed_points, 2),
                }
            )
        baseline_velocities = [float(item["completed_points"]) for item in baseline_evidence]
        baseline_sprint_count = len(baseline_velocities)
        historical_velocity = (
            round(sum(baseline_velocities) / baseline_sprint_count, 2)
            if baseline_sprint_count > 0
            else None
        )
        remaining_time_ratio = 1.0 if time_elapsed_pct is None else _clamp((100.0 - time_elapsed_pct) / 100.0)
        remaining_capacity_points = (
            round(historical_velocity * remaining_time_ratio, 2)
            if historical_velocity is not None
            else None
        )
        velocity_fit = _score_velocity_fit(
            remaining_effective_points=remaining_effective_points,
            remaining_capacity_points=remaining_capacity_points,
            baseline_sprint_count=baseline_sprint_count,
        )
        velocity_status = (
            DELIVERY_CONFIDENCE_STATUS_NOT_COMPUTED
            if baseline_sprint_count == 0
            else DELIVERY_CONFIDENCE_STATUS_PARTIAL
            if any(item["status"] == DELIVERY_CONFIDENCE_STATUS_PARTIAL for item in baseline_evidence)
            else DELIVERY_CONFIDENCE_STATUS_COMPUTED
        )
        if velocity_status == DELIVERY_CONFIDENCE_STATUS_NOT_COMPUTED:
            explanations.append(
                "Historical velocity is unavailable because no eligible closed sprint has at least 50% story-point coverage."
            )
        elif velocity_status == DELIVERY_CONFIDENCE_STATUS_PARTIAL:
            explanations.append(
                "Historical velocity is partial because at least one contributing baseline sprint has incomplete story-point coverage."
            )

        blocked_issue_ratio = 0.0 if committed_issue_count == 0 else open_blockers / committed_issue_count
        blocker_penalty = _clamp(100.0 * (1.0 - blocked_issue_ratio), 0.0, 100.0)

        scope_stability_inputs = AnalyticsService._compute_sprint_scope_stability_inputs(
            session=session,
            sprint=sprint,
            snapshot_at=snapshot_at,
            field_mapper=field_mapper,
            current_issue_count=committed_issue_count,
        )
        scope_stability_index = scope_stability_inputs["scope_stability_index"]
        scope_stability_ratio = 0.0 if scope_stability_index is None else float(scope_stability_index)
        scope_stability = _clamp(100.0 * (1.0 - scope_stability_ratio), 0.0, 100.0)

        components = {
            "progress_alignment": round(progress_alignment, 2),
            "velocity_fit": round(velocity_fit, 2),
            "blocker_penalty": round(blocker_penalty, 2),
            "scope_stability": round(scope_stability, 2),
        }
        score = round(
            sum(components[name] * DELIVERY_CONFIDENCE_WEIGHTS[name] for name in DELIVERY_CONFIDENCE_WEIGHTS),
            2,
        )

        return {
            "status": status,
            "score": score,
            "components": components,
            "coverage": coverage,
            "explanations": explanations,
            "inputs": {
                "committed_issue_count": committed_issue_count,
                "pointed_issue_count": coverage["pointed_ticket_count"],
                "committed_effective_points": round(committed_effective_points, 2),
                "completed_effective_points": round(completed_effective_points, 2),
                "remaining_effective_points": round(remaining_effective_points, 2),
                "completed_scope_pct": round(completed_scope_pct, 2),
                "time_elapsed_pct": round(time_elapsed_pct, 2) if time_elapsed_pct is not None else None,
                "historical_velocity": historical_velocity,
                "baseline_sprint_count": baseline_sprint_count,
                "baseline_sprints": baseline_evidence,
                "velocity_status": velocity_status,
                "remaining_capacity_points": remaining_capacity_points,
                "blocked_issue_ratio": round(blocked_issue_ratio, 4),
                **scope_stability_inputs,
            },
        }

    @staticmethod
    def _list_sprint_issues(session: Session, sprint_id: str) -> list[Issue]:
        return list(
            session.scalars(
                select(Issue)
                .where(Issue.issue_key.in_(AnalyticsService._sprint_issue_keys_subquery(sprint_id)))
                .order_by(Issue.issue_key)
            ).all()
        )

    @staticmethod
    def _compute_completed_effective_points_for_sprint(
        session: Session,
        sprint_id: str,
        field_mapper: JiraFieldMapper,
    ) -> float:
        issues = AnalyticsService._list_sprint_issues(session=session, sprint_id=sprint_id)
        return sum(_story_points(issue) for issue in issues if field_mapper.is_done_status(issue.status))

    @staticmethod
    def _list_velocity_baseline_sprints(session: Session, sprint: Sprint) -> list[Sprint]:
        target_start = _coerce_utc(sprint.start_date) or _coerce_utc(sprint.complete_date) or _coerce_utc(sprint.end_date)
        candidates = list(
            session.scalars(
                select(Sprint)
                .where(
                    Sprint.project_key == sprint.project_key,
                    func.lower(Sprint.state) == "closed",
                    Sprint.sprint_id != sprint.sprint_id,
                )
            ).all()
        )

        dated_candidates: list[tuple[datetime, Sprint]] = []
        for candidate in candidates:
            candidate_date = _coerce_utc(candidate.complete_date) or _coerce_utc(candidate.end_date) or _coerce_utc(
                candidate.start_date
            )
            if candidate_date is None:
                continue
            if target_start is not None and candidate_date > target_start:
                continue
            dated_candidates.append((candidate_date, candidate))

        dated_candidates.sort(key=lambda item: (item[0], item[1].sprint_id), reverse=True)
        eligible: list[Sprint] = []
        for _, candidate in dated_candidates:
            coverage = _story_point_coverage(
                AnalyticsService._list_sprint_issues(session, candidate.sprint_id)
            )
            if coverage["coverage_pct"] < MIN_STORY_POINT_COVERAGE_PCT:
                continue
            eligible.append(candidate)
            if len(eligible) == HISTORICAL_VELOCITY_SPRINT_COUNT:
                break
        return eligible

    @staticmethod
    def _compute_sprint_scope_stability_inputs(
        session: Session,
        sprint: Sprint,
        snapshot_at: datetime,
        field_mapper: JiraFieldMapper,
        current_issue_count: int,
    ) -> dict[str, object]:
        """Compute post-start scope movement as (added + removed) / initial commitment."""
        start_at = _coerce_utc(sprint.start_date)
        if start_at is None:
            return _build_scope_stability_inputs(
                added_issue_keys=[],
                removed_issue_keys=[],
                current_issue_count=current_issue_count,
            )

        snapshot_at = _coerce_utc(snapshot_at) or snapshot_at
        end_at = _coerce_utc(sprint.end_date)
        upper_bound = min(snapshot_at, end_at) if end_at is not None else snapshot_at
        if upper_bound <= start_at:
            return _build_scope_stability_inputs(
                added_issue_keys=[],
                removed_issue_keys=[],
                current_issue_count=current_issue_count,
            )

        entries = session.scalars(
            select(IssueHistory)
            .where(
                IssueHistory.issue_key.in_(
                    select(Issue.issue_key).where(
                        or_(
                            Issue.issue_key.in_(AnalyticsService._sprint_issue_keys_subquery(sprint.sprint_id)),
                            _issue_key_matches_project(Issue.issue_key, sprint.project_key),
                        )
                    )
                ),
                func.lower(IssueHistory.field_name).in_(field_mapper.sprint_changelog_fields),
                IssueHistory.changed_at > start_at,
                IssueHistory.changed_at <= upper_bound,
            )
            .order_by(IssueHistory.issue_key, IssueHistory.changed_at)
        ).all()

        added_issue_keys: set[str] = set()
        removed_issue_keys: set[str] = set()
        for entry in entries:
            old_references_sprint = _history_value_references_sprint(entry.old_value, sprint)
            new_references_sprint = _history_value_references_sprint(entry.new_value, sprint)
            if not old_references_sprint and new_references_sprint:
                added_issue_keys.add(entry.issue_key)
            elif old_references_sprint and not new_references_sprint:
                removed_issue_keys.add(entry.issue_key)

        return _build_scope_stability_inputs(
            added_issue_keys=sorted(added_issue_keys),
            removed_issue_keys=sorted(removed_issue_keys),
            current_issue_count=current_issue_count,
        )


def _story_points(issue: Issue) -> float:
    value = _valid_story_points(issue.story_points)
    return value if value is not None else 0.0


def _valid_story_points(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    numeric_value = float(value)
    if numeric_value < 0 or not math.isfinite(numeric_value):
        return None
    return numeric_value


def _story_point_coverage(issues: list[Issue]) -> dict[str, object]:
    unpointed_issue_keys = sorted(
        issue.issue_key for issue in issues if _valid_story_points(issue.story_points) is None
    )
    total_ticket_count = len(issues)
    unpointed_ticket_count = len(unpointed_issue_keys)
    pointed_ticket_count = total_ticket_count - unpointed_ticket_count
    coverage_pct = (
        0.0
        if total_ticket_count == 0
        else round(100.0 * pointed_ticket_count / total_ticket_count, 2)
    )
    return {
        "total_ticket_count": total_ticket_count,
        "pointed_ticket_count": pointed_ticket_count,
        "unpointed_ticket_count": unpointed_ticket_count,
        "coverage_pct": coverage_pct,
        "unpointed_issue_keys": unpointed_issue_keys,
    }


def _clamp(value: float, minimum: float = 0.0, maximum: float = 1.0) -> float:
    return max(minimum, min(maximum, value))


def _coerce_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _compute_time_elapsed_pct(sprint: Sprint, snapshot_at: datetime) -> float | None:
    start_at = _coerce_utc(sprint.start_date)
    end_at = _coerce_utc(sprint.end_date)
    snapshot_at = _coerce_utc(snapshot_at)
    if start_at is None or end_at is None or snapshot_at is None or end_at <= start_at:
        return None
    elapsed_seconds = (snapshot_at - start_at).total_seconds()
    total_seconds = (end_at - start_at).total_seconds()
    return _clamp(100.0 * elapsed_seconds / total_seconds, 0.0, 100.0)


def _score_progress_alignment(completed_scope_pct: float, time_elapsed_pct: float | None) -> float:
    if time_elapsed_pct is None or time_elapsed_pct <= 0:
        return 100.0
    return _clamp(100.0 * completed_scope_pct / time_elapsed_pct, 0.0, 100.0)


def _score_velocity_fit(
    remaining_effective_points: float,
    remaining_capacity_points: float | None,
    baseline_sprint_count: int,
) -> float:
    if remaining_effective_points <= 0:
        return 100.0
    if baseline_sprint_count == 0 or remaining_capacity_points is None:
        return 50.0
    if remaining_capacity_points <= 0:
        return 0.0
    return _clamp(100.0 * remaining_capacity_points / remaining_effective_points, 0.0, 100.0)


def _build_scope_stability_inputs(
    added_issue_keys: list[str],
    removed_issue_keys: list[str],
    current_issue_count: int,
) -> dict[str, object]:
    added_count = len(added_issue_keys)
    removed_count = len(removed_issue_keys)
    change_count = added_count + removed_count
    initial_commitment_count = max(current_issue_count - added_count + removed_count, 0)
    scope_stability_index = (
        None
        if initial_commitment_count == 0
        else round(change_count / initial_commitment_count, 4)
    )
    return {
        "initial_commitment_count": initial_commitment_count,
        "scope_change_count": change_count,
        "scope_added_count": added_count,
        "scope_removed_count": removed_count,
        "scope_stability_index": scope_stability_index,
        "scope_change_issue_keys": sorted(set(added_issue_keys) | set(removed_issue_keys)),
        "scope_added_issue_keys": added_issue_keys,
        "scope_removed_issue_keys": removed_issue_keys,
    }


def _history_value_references_sprint(value: str | None, sprint: Sprint) -> bool:
    if value is None:
        return False
    normalized = value.casefold()
    return sprint.sprint_id.casefold() in normalized or sprint.name.casefold() in normalized


def _issue_key_matches_project(issue_key_column, project_key: str):
    return func.upper(issue_key_column).like(f"{project_key.upper()}-%")
