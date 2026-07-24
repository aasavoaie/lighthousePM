import logging
import math
import statistics
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from typing import TypedDict, cast

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.metric_catalog import (
    RELEASE_THRESHOLD_METADATA,
    metric_minimum_coverage_pct,
    metric_threshold_value,
)
from app.models import Issue, IssueHistory, IssueSprint, MetricSnapshot, Release, Sprint, SprintMetricSnapshot
from app.repositories.operational_status_repository import OperationalStatusRepository
from app.services.jira_field_mapper import JiraFieldMapper
from app.services.confidence_breakdown_service import ConfidenceBreakdownService
from app.services.metric_availability_service import (
    COMPUTATION_STATUS_COMPUTED,
    COMPUTATION_STATUS_NOT_APPLICABLE,
    COMPUTATION_STATUS_NOT_COMPUTED,
    COMPUTATION_STATUS_PARTIAL,
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
    RULESET_VERSION,
)

logger = logging.getLogger(__name__)

MIN_STORY_POINT_COVERAGE_PCT = metric_minimum_coverage_pct(
    "sprint.delivery_confidence_score"
)
WORKLOAD_CONCENTRATION_CRITICAL_MIN_EXCLUSIVE_PCT = metric_threshold_value(
    "sprint.workload_concentration_pct", "critical"
)
WORKLOAD_CONCENTRATION_WATCH_MIN_PCT = metric_threshold_value(
    "sprint.workload_concentration_pct", "watch"
)

DELIVERY_CONFIDENCE_WEIGHTS = {
    "progress_alignment": 0.4,
    "velocity_fit": 0.3,
    "blocker_penalty": 0.2,
    "scope_stability": 0.1,
}
HISTORICAL_VELOCITY_SPRINT_COUNT = 3


class _StoryPointCoverage(TypedDict):
    total_ticket_count: int
    pointed_ticket_count: int
    unpointed_ticket_count: int
    coverage_pct: float
    unpointed_issue_keys: list[str]


class _ScopeChurnResult(TypedDict):
    status: str
    scope_churn_7d_pct: float | None
    scope_added_7d_count: int
    scope_removed_7d_count: int
    explanations: list[str]
    missing_issue_keys: list[str]
    evidence: dict[str, object]


class _BugsCreatedDuringSprintResult(TypedDict):
    status: str
    issue_keys: list[str]
    missing_created_at_issue_keys: list[str]


class _ScopeStabilityInputs(TypedDict):
    initial_commitment_count: int
    scope_change_count: int
    scope_added_count: int
    scope_removed_count: int
    scope_stability_index: float | None
    scope_change_issue_keys: list[str]
    scope_added_issue_keys: list[str]
    scope_removed_issue_keys: list[str]


class _VelocityBaselineEvidence(TypedDict):
    sprint_id: str
    coverage_pct: float
    status: str
    completed_points: float


class _DeliveryConfidenceResult(TypedDict):
    status: str
    score: float | None
    components: dict[str, float] | None
    inputs: dict[str, object] | None
    coverage: _StoryPointCoverage
    prerequisites: dict[str, object]
    explanations: list[str]


class _WorkloadBucket(TypedDict):
    assignee_key: str
    labels: list[str]
    story_points: float
    issue_keys: list[str]


class _AssigneeTotal(TypedDict):
    assignee_key: str
    assignee: str
    story_points: float
    issue_keys: list[str]


class AnalyticsService:
    """Deterministic metrics computation for a single release.

    All methods are pure functions over stored Jira data — no Jira API calls.
    The caller owns the session transaction; recompute_release_metrics does not commit.

    Assumptions are documented in PRODUCT_RULES.md, the metric catalog, and inline below.
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

        snapshot_at = datetime.now(UTC)
        field_mapper = JiraFieldMapper(get_settings())

        classification_results = MetricAvailabilityService.evaluate_release_classification_metrics(
            session=session,
            release_id=release_id,
            field_mapper=field_mapper,
        )
        open_blocker_issue_keys = classification_results["open_blockers"]["evidence"]["matching_issue_keys"]
        open_high_severity_bug_issue_keys = classification_results["open_high_severity_bugs"]["evidence"][
            "matching_issue_keys"
        ]
        scope_churn_7d = self._compute_release_scope_churn_7d(
            session=session,
            release_id=release_id,
            project_key=release.project_key,
            release_name=release.name,
            field_mapper=field_mapper,
            snapshot_at=snapshot_at,
        )

        ticket_count = int(
            session.scalar(
                select(func.count()).select_from(Issue).where(Issue.release_id == release_id)
            )
            or 0
        )
        scope_completed_pct = classification_results["scope_completed_pct"]["value"]
        completed_tickets = classification_results["completed_tickets"]["value"]
        flow_metrics = self.evaluate_release_flow_metrics(session, release_id, field_mapper)
        reopen_rate_result = flow_metrics["reopen_rate_pct"]
        cycle_time_result = flow_metrics["median_cycle_time_days"]
        reopen_rate_pct = cast(
            float | None,
            reopen_rate_result["reopen_rate_pct"],
        )
        median_cycle_time_days = cast(
            float | None,
            cycle_time_result["median_cycle_time_days"],
        )
        scope_churn_7d_pct = scope_churn_7d["scope_churn_7d_pct"]
        classification_confidence_partial = any(
            classification_results[metric_name]["status"] == "PARTIAL"
            for metric_name in ("open_blockers", "open_high_severity_bugs")
        )
        release_confidence_partial = (
            classification_confidence_partial
            or scope_churn_7d["status"] == "PARTIAL"
            or any(result["status"] == "PARTIAL" for result in flow_metrics.values())
        )
        release_confidence_unavailable = (
            release_confidence_partial
            or any(result["status"] != "COMPUTED" for result in flow_metrics.values())
        )
        confidence_score = (
            SignalService._compute_release_confidence_score(
                open_blockers=len(open_blocker_issue_keys),
                open_high_severity_bugs=len(open_high_severity_bug_issue_keys),
                scope_churn_7d_pct=scope_churn_7d_pct,
                reopen_rate_pct=reopen_rate_pct,
                median_cycle_time_days=median_cycle_time_days,
            )
            if ticket_count > 0
            and not release_confidence_unavailable
            and scope_churn_7d_pct is not None
            and reopen_rate_pct is not None
            else None
        )
        snapshot = MetricSnapshot(
            release_id=release_id,
            snapshot_at=snapshot_at,
            ruleset_version=RULESET_VERSION,
            confidence_score=confidence_score,
            confidence_status=(
                "PARTIAL"
                if release_confidence_partial
                else "COMPUTED" if confidence_score is not None else "NOT_COMPUTED"
            ),
            open_blockers=len(open_blocker_issue_keys),
            open_high_severity_bugs=len(open_high_severity_bug_issue_keys),
            open_blocker_issue_keys=open_blocker_issue_keys,
            open_high_severity_bug_issue_keys=open_high_severity_bug_issue_keys,
            scope_completed_pct=scope_completed_pct if scope_completed_pct is not None else 0.0,
            completed_tickets=int(completed_tickets or 0),
            scope_churn_7d_pct=scope_churn_7d_pct,
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
            classification_results=classification_results,
            scope_churn_7d=scope_churn_7d,
            flow_metrics=flow_metrics,
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
        The rollover_count compatibility field is only populated for closed
        sprints and means current sprint-membership tickets with a known status
        outside the configured done set. It does not prove movement to another
        sprint.
        """
        sprint = session.scalar(select(Sprint).where(Sprint.sprint_id == sprint_id))
        if sprint is None:
            raise ValueError(f"Sprint not found: {sprint_id!r}")

        logger.info("sprint_metrics_recompute_started sprint_id=%s", sprint_id)
        field_mapper = JiraFieldMapper(get_settings())

        classification_results = MetricAvailabilityService.evaluate_sprint_classification_metrics(
            session=session,
            sprint_id=sprint_id,
            field_mapper=field_mapper,
        )
        scope_metrics = MetricAvailabilityService.evaluate_sprint_scope_metrics(
            session=session,
            sprint_id=sprint_id,
            field_mapper=field_mapper,
        )
        work_state_metrics = MetricAvailabilityService.evaluate_sprint_work_state_metrics(
            session=session,
            sprint_id=sprint_id,
            field_mapper=field_mapper,
        )
        workload_distribution = self._compute_workload_distribution(
            session=session,
            sprint_id=sprint_id,
            field_mapper=field_mapper,
        )
        open_blocker_issue_keys = classification_results["open_blockers"]["evidence"]["matching_issue_keys"]
        open_high_severity_bug_issue_keys = classification_results["open_high_severity_bugs"]["evidence"][
            "matching_issue_keys"
        ]
        snapshot_at = datetime.now(UTC)
        bugs_created_during_sprint = self._compute_bugs_created_during_sprint(
            session=session,
            sprint=sprint,
            snapshot_at=snapshot_at,
            field_mapper=field_mapper,
        )
        flow_metrics = self.evaluate_sprint_flow_metrics(session, sprint_id, field_mapper)
        delivery_confidence_prerequisites = (
            MetricAvailabilityService.evaluate_sprint_delivery_confidence_prerequisites(
                session=session,
                sprint_id=sprint_id,
                field_mapper=field_mapper,
                classification_results=classification_results,
            )
        )
        delivery_confidence = self._compute_delivery_confidence(
            session=session,
            sprint=sprint,
            snapshot_at=snapshot_at,
            field_mapper=field_mapper,
            open_blockers=len(open_blocker_issue_keys),
            prerequisites=delivery_confidence_prerequisites,
        )

        snapshot = SprintMetricSnapshot(
            sprint_id=sprint_id,
            snapshot_at=snapshot_at,
            ruleset_version=RULESET_VERSION,
            committed_scope=scope_metrics["committed_scope"]["value"],
            completed_scope_pct=scope_metrics["completed_scope_pct"]["value"],
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
            in_progress_count=work_state_metrics["in_progress_count"]["value"],
            not_started_count=work_state_metrics["not_started_count"]["value"],
            rollover_count=work_state_metrics["rollover_count"]["value"],
            median_cycle_time_days=flow_metrics["median_cycle_time_days"]["median_cycle_time_days"],
            reopen_rate_pct=flow_metrics["reopen_rate_pct"]["reopen_rate_pct"],
            workload_concentration_pct=workload_distribution["value"],
            workload_distribution_status=workload_distribution["status"],
            workload_distribution_explanations=workload_distribution["explanations"],
            workload_distribution_evidence=workload_distribution["evidence"],
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
            classification_results=classification_results,
            flow_metrics=flow_metrics,
            scope_metrics=scope_metrics,
            work_state_metrics=work_state_metrics,
            delivery_confidence_result=delivery_confidence,
            workload_distribution=workload_distribution,
        )
        session.add(snapshot)
        OperationalStatusRepository.mark_metrics_recomputed(session=session)
        logger.info(
            "sprint_metrics_recompute_completed sprint_id=%s current_scope=%s completed_scope_pct=%s",
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
            "bug_issue_types": sorted(field_mapper.bug_issue_types),
            "blocker_issue_types": sorted(field_mapper.blocker_issue_types),
            "blocker_severity_values": sorted(field_mapper.blocker_severity_values),
            "blocked_statuses": sorted(field_mapper.blocked_statuses),
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
        classification_results: dict[str, dict[str, object]],
        scope_churn_7d: _ScopeChurnResult,
        flow_metrics: dict[str, dict[str, object]],
    ) -> dict[str, object]:
        from app.services.driver_analysis_service import DriverAnalysisService

        classification_confidence_partial = any(
            classification_results[metric_name]["status"] == "PARTIAL"
            for metric_name in ("open_blockers", "open_high_severity_bugs")
        )
        release_confidence_partial = (
            classification_confidence_partial
            or scope_churn_7d["status"] == "PARTIAL"
            or any(result["status"] == "PARTIAL" for result in flow_metrics.values())
        )
        release_confidence_unavailable = (
            release_confidence_partial
            or any(result["status"] != "COMPUTED" for result in flow_metrics.values())
        )
        readiness_inputs_partial = release_confidence_partial
        reopen_rate_available = flow_metrics["reopen_rate_pct"]["status"] == "COMPUTED"
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
            and not readiness_inputs_partial
            and reopen_rate_available
            and snapshot.scope_churn_7d_pct is not None
            else {}
        )
        availability = MetricAvailabilityService.build_release_availability(
            session=session,
            release_id=release_id,
            field_mapper=field_mapper,
            scope_churn_result=cast(dict[str, object], scope_churn_7d),
            flow_metric_results=flow_metrics,
        )
        computation_status, unavailable_reason = MetricAvailabilityService.computation_state(
            availability,
            is_computed=True,
            empty_scope_reason=UNAVAILABLE_REASON_RELEASE_EMPTY,
        )
        return {
            "source_calculated_at": snapshot.snapshot_at.isoformat(),
            "thresholds": dict(RELEASE_THRESHOLD_METADATA),
            "weights": dict(SignalService.RISK_WEIGHTS),
            "classification": AnalyticsService._classification_provenance(field_mapper),
            "availability": availability.model_dump(),
            "computation_status": computation_status,
            "unavailable_reason": unavailable_reason,
            "story_point_coverage": None,
            "scope_churn_7d": scope_churn_7d["evidence"],
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
                "risk_points": (
                    SignalService._compute_release_risk_points(
                        open_blockers=snapshot.open_blockers,
                        open_high_severity_bugs=snapshot.open_high_severity_bugs,
                        scope_churn_7d_pct=snapshot.scope_churn_7d_pct,
                        reopen_rate_pct=snapshot.reopen_rate_pct,
                        median_cycle_time_days=snapshot.median_cycle_time_days,
                    )
                    if not release_confidence_unavailable
                    and snapshot.scope_churn_7d_pct is not None
                    else None
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
                        * sum(
                            1
                            for gate in cast(
                                list[dict[str, object]],
                                readiness.get("release_gates", []),
                            )
                            if gate.get("passed") is True
                        )
                        / len(
                            cast(
                                list[dict[str, object]],
                                readiness.get("release_gates", []),
                            )
                        ),
                        2,
                    )
                    if readiness.get("release_gates")
                    else None
                ),
            },
            "issue_key_evidence": {
                "open_blockers": snapshot.open_blocker_issue_keys,
                "open_high_severity_bugs": snapshot.open_high_severity_bug_issue_keys,
                "completed_tickets": cast(
                    dict[str, object],
                    classification_results["completed_tickets"]["evidence"],
                )["matching_issue_keys"],
                "scope_added_7d": scope_churn_7d["evidence"]["added_issue_keys"],
                "scope_removed_7d": scope_churn_7d["evidence"]["removed_issue_keys"],
            },
            "metric_evidence": {
                **{
                    metric_name: result["evidence"]
                    for metric_name, result in classification_results.items()
                },
                "scope_churn_7d_pct": scope_churn_7d["evidence"],
                "scope_added_7d_count": scope_churn_7d["evidence"],
                "scope_removed_7d_count": scope_churn_7d["evidence"],
                "median_cycle_time_days": flow_metrics["median_cycle_time_days"]["evidence"],
                "reopen_rate_pct": flow_metrics["reopen_rate_pct"]["evidence"],
            },
        }

    @staticmethod
    def _sprint_calculation_provenance(
        session: Session,
        sprint_id: str,
        snapshot: SprintMetricSnapshot,
        field_mapper: JiraFieldMapper,
        classification_results: dict[str, dict[str, object]],
        flow_metrics: dict[str, dict[str, object]],
        scope_metrics: dict[str, dict[str, object]],
        work_state_metrics: dict[str, dict[str, object]],
        delivery_confidence_result: _DeliveryConfidenceResult,
        workload_distribution: dict[str, object],
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
            flow_metric_results=flow_metrics,
            scope_metric_results=scope_metrics,
            work_state_metric_results=work_state_metrics,
            delivery_confidence_result=cast(
                dict[str, object],
                delivery_confidence_result,
            ),
            workload_distribution_result=workload_distribution,
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
            "delivery_confidence_prerequisites": delivery_confidence_result[
                "prerequisites"
            ],
            "workload_distribution": workload_distribution,
            "history_completeness": AnalyticsService._history_completeness_evidence(
                session,
                AnalyticsService._sprint_issue_keys_subquery(sprint_id),
            ),
            "component_inputs": snapshot.delivery_confidence_inputs,
            "component_outputs": {
                "components": snapshot.delivery_confidence_components,
                "confidence_breakdown": (
                    ConfidenceBreakdownService.build_sprint_breakdown(
                        score=cast(float, snapshot.delivery_confidence_score),
                        components=snapshot.delivery_confidence_components or {},
                        inputs=snapshot.delivery_confidence_inputs,
                    ).model_dump()
                    if has_confidence
                    else None
                ),
                "biggest_driver": (
                    DriverAnalysisService.build_sprint_driver(
                        score=cast(float, snapshot.delivery_confidence_score),
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
            "metric_evidence": {
                **{
                    metric_name: result["evidence"]
                    for metric_name, result in classification_results.items()
                },
                "median_cycle_time_days": flow_metrics["median_cycle_time_days"]["evidence"],
                "reopen_rate_pct": flow_metrics["reopen_rate_pct"]["evidence"],
                "committed_scope": scope_metrics["committed_scope"]["evidence"],
                "completed_scope_pct": scope_metrics["completed_scope_pct"]["evidence"],
                "in_progress_count": work_state_metrics["in_progress_count"]["evidence"],
                "not_started_count": work_state_metrics["not_started_count"]["evidence"],
                "rollover_count": work_state_metrics["rollover_count"]["evidence"],
                "workload_concentration_pct": workload_distribution["evidence"],
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
    def _compute_release_scope_churn_7d(
        session: Session,
        release_id: str,
        project_key: str,
        release_name: str,
        field_mapper: JiraFieldMapper,
        snapshot_at: datetime,
    ) -> _ScopeChurnResult:
        """Evaluate seven-day release scope churn from stored Jira evidence."""
        window_end = _coerce_utc(snapshot_at)
        assert window_end is not None
        window_start = window_end - timedelta(days=7)
        normalized_release_value = release_name.strip().casefold()

        project_issues = list(
            session.scalars(
                select(Issue)
                .where(
                    or_(
                        Issue.release_id == release_id,
                        _issue_key_matches_project(Issue.issue_key, project_key),
                    )
                )
                .order_by(Issue.issue_key)
            ).all()
        )
        project_issue_keys = [issue.issue_key for issue in project_issues]
        current_scope_issue_keys = list(
            session.scalars(
                select(Issue.issue_key)
                .where(Issue.release_id == release_id)
                .order_by(Issue.issue_key)
            ).all()
        )
        incomplete_project_changelog_issue_keys = [
            issue.issue_key for issue in project_issues if not issue.jira_changelog_complete
        ]

        entries = (
            list(
                session.scalars(
                    select(IssueHistory)
                    .where(
                        IssueHistory.issue_key.in_(project_issue_keys),
                        IssueHistory.changed_at >= window_start,
                        IssueHistory.changed_at <= window_end,
                    )
                    .order_by(
                        IssueHistory.issue_key,
                        IssueHistory.changed_at,
                        IssueHistory.id,
                    )
                ).all()
            )
            if project_issue_keys
            else []
        )

        added_keys: set[str] = set()
        removed_keys: set[str] = set()
        for entry in entries:
            if not field_mapper.is_fix_version_field(entry.field_name):
                continue
            old_references_release = _history_value_references_release(
                entry.old_value,
                normalized_release_value,
            )
            new_references_release = _history_value_references_release(
                entry.new_value,
                normalized_release_value,
            )
            if not old_references_release and new_references_release:
                added_keys.add(entry.issue_key)
            elif old_references_release and not new_references_release:
                removed_keys.add(entry.issue_key)

        sorted_added_keys = sorted(added_keys)
        sorted_removed_keys = sorted(removed_keys)
        churned_issue_keys = sorted(added_keys | removed_keys)
        observed_scope_issue_keys = sorted(set(current_scope_issue_keys) | set(churned_issue_keys))
        denominator = len(observed_scope_issue_keys)

        if incomplete_project_changelog_issue_keys:
            status = "PARTIAL"
            scope_churn_7d_pct = None
            explanations = [
                "Scope churn is partial because Jira changelog ingestion is incomplete for "
                f"{len(incomplete_project_changelog_issue_keys)} project ticket(s). Added and "
                "removed counts are confirmed minima; the percentage is unavailable."
            ]
        elif denominator == 0:
            status = "NOT_COMPUTED"
            scope_churn_7d_pct = None
            explanations = [
                "Scope churn is not computed because no current or changed release scope was "
                "observed in the seven-day window."
            ]
        else:
            status = "COMPUTED"
            scope_churn_7d_pct = round(100.0 * len(churned_issue_keys) / denominator, 2)
            explanations = []

        return {
            "status": status,
            "scope_churn_7d_pct": scope_churn_7d_pct,
            "scope_added_7d_count": len(sorted_added_keys),
            "scope_removed_7d_count": len(sorted_removed_keys),
            "explanations": explanations,
            "missing_issue_keys": incomplete_project_changelog_issue_keys,
            "evidence": {
                "window_start": window_start.isoformat(),
                "window_end": window_end.isoformat(),
                "synchronized_project_issue_keys": project_issue_keys,
                "current_scope_issue_keys": current_scope_issue_keys,
                "observed_scope_issue_keys": observed_scope_issue_keys,
                "observed_scope_denominator": denominator,
                "churned_issue_keys": churned_issue_keys,
                "added_issue_keys": sorted_added_keys,
                "removed_issue_keys": sorted_removed_keys,
                "incomplete_project_changelog_issue_keys": (
                    incomplete_project_changelog_issue_keys
                ),
                "configured_changelog_aliases": sorted(
                    field_mapper.fix_version_changelog_fields
                ),
                "normalized_release_value": normalized_release_value,
            },
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
    def evaluate_release_flow_metrics(
        session: Session,
        release_id: str,
        field_mapper: JiraFieldMapper,
    ) -> dict[str, dict[str, object]]:
        """Evaluate the approved cycle-time and reopen-event contracts for a release.

        This evaluator is intentionally separate from snapshot persistence. Phase 2.4.2
        will wire these structured results into stored snapshots and API availability.
        """
        issues = list(
            session.scalars(
                select(Issue)
                .where(Issue.release_id == release_id)
                .order_by(Issue.issue_key)
            ).all()
        )
        return _evaluate_flow_metrics(
            issues=issues,
            status_histories=_load_status_histories(session, [issue.issue_key for issue in issues]),
            field_mapper=field_mapper,
        )

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
    def _compute_bugs_created_during_sprint(
        session: Session,
        sprint: Sprint,
        snapshot_at: datetime,
        field_mapper: JiraFieldMapper,
    ) -> _BugsCreatedDuringSprintResult:
        """Sorted sprint bug keys where issue creation falls inside the sprint window.

        The window starts at sprint.start_date. It ends at complete_date for closed
        sprints when present, otherwise end_date, capped at snapshot_at for active
        sprints whose configured end date is in the future.
        """
        start_at = _coerce_utc(sprint.start_date)
        normalized_snapshot_at = _coerce_utc(snapshot_at)
        assert normalized_snapshot_at is not None
        if start_at is None:
            return {
                "status": "NOT_COMPUTED",
                "issue_keys": [],
                "missing_created_at_issue_keys": [],
            }

        if sprint.state.casefold() == "closed":
            upper_bound = (
                _coerce_utc(sprint.complete_date)
                or _coerce_utc(sprint.end_date)
                or normalized_snapshot_at
            )
        else:
            configured_end_at = _coerce_utc(sprint.end_date)
            upper_bound = (
                min(configured_end_at, normalized_snapshot_at)
                if configured_end_at is not None
                else normalized_snapshot_at
            )
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
                    func.lower(Issue.issue_type).in_(field_mapper.bug_issue_types),
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
    def evaluate_sprint_flow_metrics(
        session: Session,
        sprint_id: str,
        field_mapper: JiraFieldMapper,
    ) -> dict[str, dict[str, object]]:
        """Evaluate the approved flow metrics for current sprint membership."""
        sprint_issue_keys = AnalyticsService._sprint_issue_keys_subquery(sprint_id)
        issues = list(
            session.scalars(
                select(Issue)
                .where(Issue.issue_key.in_(sprint_issue_keys))
                .order_by(Issue.issue_key)
            ).all()
        )
        return _evaluate_flow_metrics(
            issues=issues,
            status_histories=_load_status_histories(session, [issue.issue_key for issue in issues]),
            field_mapper=field_mapper,
        )

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
    def _compute_workload_distribution(
        session: Session,
        sprint_id: str,
        field_mapper: JiraFieldMapper,
    ) -> dict[str, object]:
        """Compute authoritative workload concentration from current sprint scope."""
        issues = AnalyticsService._list_sprint_issues(session, sprint_id)
        coverage = _story_point_coverage(issues)
        current_scope_issue_keys = [issue.issue_key for issue in issues]
        missing_status_issue_keys = sorted(
            issue.issue_key for issue in issues if not _normalize_text(issue.status)
        )
        active_issues = [
            issue
            for issue in issues
            if _normalize_text(issue.status) and not field_mapper.is_done_status(issue.status)
        ]
        active_issue_keys = sorted(issue.issue_key for issue in active_issues)

        def evidence(
            *,
            calculation_status: str,
            workload_concentration_pct: float | None = None,
            included_active_issue_keys: list[str] | None = None,
            excluded_active_issue_keys: list[str] | None = None,
            fallback_issue_keys: list[str] | None = None,
            assignee_totals: Sequence[_AssigneeTotal] | None = None,
            total_active_points: float | None = None,
            top_assignee: _AssigneeTotal | None = None,
            risk_band: str | None = None,
        ) -> dict[str, object]:
            return {
                "calculation_status": calculation_status,
                "workload_concentration_pct": workload_concentration_pct,
                "current_scope_issue_keys": current_scope_issue_keys,
                "active_issue_keys": active_issue_keys,
                "included_active_issue_keys": included_active_issue_keys or [],
                "excluded_active_issue_keys": excluded_active_issue_keys or [],
                "missing_status_issue_keys": missing_status_issue_keys,
                "assignee_identity_fallback_issue_keys": fallback_issue_keys or [],
                "assignee_totals": list(assignee_totals or []),
                "total_active_points": total_active_points,
                "top_assignee": top_assignee,
                "risk_band": risk_band,
                "story_point_coverage": coverage,
            }

        if not issues:
            explanation = "Workload distribution is not computed because the sprint has no tickets."
            return {
                "status": COMPUTATION_STATUS_NOT_COMPUTED,
                "value": None,
                "explanations": [explanation],
                "missing_issue_keys": [],
                "evidence": evidence(calculation_status=COMPUTATION_STATUS_NOT_COMPUTED),
            }

        inconclusive_explanations: list[str] = []
        if coverage["coverage_pct"] < MIN_STORY_POINT_COVERAGE_PCT:
            inconclusive_explanations.append(
                "Workload distribution is inconclusive because fewer than 50% of current-sprint "
                "tickets have valid story points."
            )
        if missing_status_issue_keys:
            inconclusive_explanations.append(
                "Workload distribution is inconclusive because current-sprint tickets are "
                "missing status: " + ", ".join(missing_status_issue_keys) + "."
            )
        if inconclusive_explanations:
            return {
                "status": "INCONCLUSIVE",
                "value": None,
                "explanations": inconclusive_explanations,
                "missing_issue_keys": sorted(
                    set(coverage["unpointed_issue_keys"]) | set(missing_status_issue_keys)
                ),
                "evidence": evidence(calculation_status="INCONCLUSIVE"),
            }

        if not active_issues:
            explanation = "Workload distribution does not apply because the sprint has no active tickets."
            return {
                "status": COMPUTATION_STATUS_NOT_APPLICABLE,
                "value": None,
                "explanations": [explanation],
                "missing_issue_keys": [],
                "evidence": evidence(calculation_status=COMPUTATION_STATUS_NOT_APPLICABLE),
            }

        included: list[tuple[Issue, float]] = []
        excluded_active_issue_keys: list[str] = []
        for issue in active_issues:
            points = _valid_story_points(issue.story_points)
            if points is None:
                excluded_active_issue_keys.append(issue.issue_key)
            else:
                included.append((issue, points))
        included_active_issue_keys = sorted(issue.issue_key for issue, _points in included)
        excluded_active_issue_keys.sort()

        buckets: dict[str, _WorkloadBucket] = {}
        fallback_issue_keys: list[str] = []
        for issue, points in included:
            display_name = (issue.assignee or "").strip()
            stable_id = (issue.jira_assignee_id or "").strip()
            if not display_name and not stable_id:
                bucket_key = "unassigned"
                label = "Unassigned"
            elif stable_id:
                bucket_key = f"jira:{stable_id}"
                label = display_name or stable_id
            else:
                bucket_key = f"display:{display_name.casefold()}"
                label = display_name
                fallback_issue_keys.append(issue.issue_key)

            bucket = buckets.setdefault(
                bucket_key,
                {
                    "assignee_key": bucket_key,
                    "labels": [],
                    "story_points": 0.0,
                    "issue_keys": [],
                },
            )
            bucket["labels"].append(label)
            bucket["story_points"] = float(bucket["story_points"]) + points
            bucket["issue_keys"].append(issue.issue_key)

        assignee_totals: list[_AssigneeTotal] = []
        for bucket in buckets.values():
            labels = sorted(set(str(label).strip() for label in bucket["labels"]))
            assignee_totals.append(
                {
                    "assignee_key": bucket["assignee_key"],
                    "assignee": labels[0],
                    "story_points": round(float(bucket["story_points"]), 2),
                    "issue_keys": sorted(str(key) for key in bucket["issue_keys"]),
                }
            )
        assignee_totals.sort(
            key=lambda item: (str(item["assignee"]).casefold(), str(item["assignee_key"]))
        )
        total_active_points = round(
            sum(float(item["story_points"]) for item in assignee_totals),
            2,
        )
        fallback_issue_keys.sort()

        if total_active_points <= 0:
            explanation = (
                "Workload distribution is not computed because included active story points sum to zero."
            )
            return {
                "status": COMPUTATION_STATUS_NOT_COMPUTED,
                "value": None,
                "explanations": [explanation],
                "missing_issue_keys": excluded_active_issue_keys + fallback_issue_keys,
                "evidence": evidence(
                    calculation_status=COMPUTATION_STATUS_NOT_COMPUTED,
                    included_active_issue_keys=included_active_issue_keys,
                    excluded_active_issue_keys=excluded_active_issue_keys,
                    fallback_issue_keys=fallback_issue_keys,
                    assignee_totals=assignee_totals,
                    total_active_points=total_active_points,
                ),
            }

        top = sorted(
            assignee_totals,
            key=lambda item: (
                -float(item["story_points"]),
                str(item["assignee"]).casefold(),
                str(item["assignee_key"]),
            ),
        )[0]
        concentration_pct = round(
            100.0 * float(top["story_points"]) / total_active_points,
            2,
        )
        risk_band = (
            "critical"
            if concentration_pct > WORKLOAD_CONCENTRATION_CRITICAL_MIN_EXCLUSIVE_PCT
            else "watch"
            if concentration_pct >= WORKLOAD_CONCENTRATION_WATCH_MIN_PCT
            else "healthy"
        )
        is_partial = coverage["coverage_pct"] < 100.0 or bool(fallback_issue_keys)
        explanations: list[str] = []
        if coverage["coverage_pct"] < 100.0:
            explanations.append(
                "Workload distribution is partial because current-sprint story-point coverage is "
                f"{coverage['coverage_pct']}%, below 100%."
            )
            if excluded_active_issue_keys:
                explanations.append(
                    "Unpointed active tickets are excluded: "
                    + ", ".join(excluded_active_issue_keys)
                    + "."
                )
            else:
                explanations.append(
                    "No active ticket is excluded, but incomplete current-sprint coverage still "
                    "makes the result partial."
                )
        if fallback_issue_keys:
            explanations.append(
                "Workload distribution is partial because normalized assignee display-name "
                "fallback is used for: " + ", ".join(fallback_issue_keys) + "."
            )
        top_assignee = _AssigneeTotal(
            assignee_key=top["assignee_key"],
            assignee=top["assignee"],
            story_points=top["story_points"],
            issue_keys=top["issue_keys"],
        )
        return {
            "status": COMPUTATION_STATUS_PARTIAL if is_partial else COMPUTATION_STATUS_COMPUTED,
            "value": concentration_pct,
            "explanations": explanations,
            "missing_issue_keys": sorted(
                set(excluded_active_issue_keys) | set(fallback_issue_keys)
            ),
            "evidence": evidence(
                calculation_status=(
                    COMPUTATION_STATUS_PARTIAL if is_partial else COMPUTATION_STATUS_COMPUTED
                ),
                workload_concentration_pct=concentration_pct,
                included_active_issue_keys=included_active_issue_keys,
                excluded_active_issue_keys=excluded_active_issue_keys,
                fallback_issue_keys=fallback_issue_keys,
                assignee_totals=assignee_totals,
                total_active_points=total_active_points,
                top_assignee=top_assignee,
                risk_band=risk_band,
            ),
        }

    @staticmethod
    def _compute_delivery_confidence(
        session: Session,
        sprint: Sprint,
        snapshot_at: datetime,
        field_mapper: JiraFieldMapper,
        open_blockers: int,
        prerequisites: dict[str, object],
    ) -> _DeliveryConfidenceResult:
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
                "prerequisites": prerequisites,
                "explanations": [
                    "Delivery confidence is not computed because the sprint has no tickets to evaluate."
                ],
            }
        coverage_explanations: list[str] = []
        if coverage["coverage_pct"] < MIN_STORY_POINT_COVERAGE_PCT:
            coverage_explanations.append(
                "Delivery confidence is inconclusive because fewer than 50% of the sprint tickets have story "
                "points. At least 50% of the tickets inside the sprint must have story points to calculate "
                "delivery confidence. Ideally, all tickets should have story points."
            )
        prerequisite_explanations = [
            str(item)
            for item in cast(
                Sequence[object],
                prerequisites.get("explanations", []),
            )
        ]
        if coverage_explanations or not bool(prerequisites["available"]):
            return {
                "status": DELIVERY_CONFIDENCE_STATUS_INCONCLUSIVE,
                "score": None,
                "components": None,
                "inputs": None,
                "coverage": coverage,
                "prerequisites": prerequisites,
                "explanations": coverage_explanations + prerequisite_explanations,
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
        if time_elapsed_pct is None:
            raise RuntimeError("Valid sprint duration did not produce elapsed time.")
        progress_alignment = _score_progress_alignment(
            completed_scope_pct=completed_scope_pct,
            time_elapsed_pct=time_elapsed_pct,
        )

        baseline_sprints = AnalyticsService._list_velocity_baseline_sprints(session=session, sprint=sprint)
        baseline_evidence: list[_VelocityBaselineEvidence] = []
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
        remaining_time_ratio = _clamp((100.0 - time_elapsed_pct) / 100.0)
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
            status = DELIVERY_CONFIDENCE_STATUS_PARTIAL
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
            "prerequisites": prerequisites,
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
    ) -> _ScopeStabilityInputs:
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


def _load_status_histories(
    session: Session,
    issue_keys: Sequence[str],
) -> dict[str, list[IssueHistory]]:
    histories_by_issue: dict[str, list[IssueHistory]] = {
        issue_key: [] for issue_key in issue_keys
    }
    if not issue_keys:
        return histories_by_issue

    histories = session.scalars(
        select(IssueHistory)
        .where(IssueHistory.issue_key.in_(issue_keys))
        .order_by(IssueHistory.issue_key, IssueHistory.changed_at, IssueHistory.id)
    ).all()
    for history in histories:
        if _normalize_text(history.field_name) == "status":
            histories_by_issue[history.issue_key].append(history)
    return histories_by_issue


def _evaluate_flow_metrics(
    issues: Sequence[Issue],
    status_histories: dict[str, list[IssueHistory]],
    field_mapper: JiraFieldMapper,
) -> dict[str, dict[str, object]]:
    return {
        "median_cycle_time_days": _evaluate_cycle_time(
            issues=issues,
            status_histories=status_histories,
            field_mapper=field_mapper,
        ),
        "reopen_rate_pct": _evaluate_reopen_event_rate(
            issues=issues,
            status_histories=status_histories,
            field_mapper=field_mapper,
        ),
    }


def _evaluate_cycle_time(
    issues: Sequence[Issue],
    status_histories: dict[str, list[IssueHistory]],
    field_mapper: JiraFieldMapper,
) -> dict[str, object]:
    scoped_issue_keys = sorted(issue.issue_key for issue in issues)
    missing_status_issue_keys: list[str] = []
    incomplete_history_issue_keys: list[str] = []
    invalid_timestamp_issue_keys: list[str] = []
    no_in_progress_issue_keys: list[str] = []
    no_later_done_issue_keys: list[str] = []
    included_issues: list[dict[str, object]] = []
    cycle_durations: list[float] = []

    for issue in sorted(issues, key=lambda item: item.issue_key):
        if not _normalize_text(issue.status):
            missing_status_issue_keys.append(issue.issue_key)
            continue
        if not field_mapper.is_done_status(issue.status):
            continue
        if not issue.jira_changelog_complete:
            incomplete_history_issue_keys.append(issue.issue_key)
            continue

        histories = status_histories.get(issue.issue_key, [])
        relevant_invalid_timestamp = any(
            not isinstance(history.changed_at, datetime)
            and (
                field_mapper.is_in_progress_status(history.new_value)
                or field_mapper.is_done_status(history.new_value)
            )
            for history in histories
        )
        if relevant_invalid_timestamp:
            invalid_timestamp_issue_keys.append(issue.issue_key)
            continue

        started_candidates = sorted(
            timestamp
            for history in histories
            if field_mapper.is_in_progress_status(history.new_value)
            and (timestamp := _coerce_utc(history.changed_at)) is not None
        )
        if not started_candidates:
            no_in_progress_issue_keys.append(issue.issue_key)
            continue

        started_at = started_candidates[0]
        ended_candidates = sorted(
            timestamp
            for history in histories
            if field_mapper.is_done_status(history.new_value)
            and (timestamp := _coerce_utc(history.changed_at)) is not None
            and timestamp > started_at
        )
        if not ended_candidates:
            no_later_done_issue_keys.append(issue.issue_key)
            continue

        ended_at = ended_candidates[0]
        duration_days = (ended_at - started_at).total_seconds() / 86_400
        cycle_durations.append(duration_days)
        included_issues.append(
            {
                "issue_key": issue.issue_key,
                "start_at": started_at.isoformat(),
                "end_at": ended_at.isoformat(),
                "duration_days": round(duration_days, 4),
            }
        )

    partial_issue_keys = sorted(
        set(missing_status_issue_keys) | set(incomplete_history_issue_keys)
    )
    if partial_issue_keys:
        status = "PARTIAL"
        value = None
    elif cycle_durations:
        status = "COMPUTED"
        value = round(statistics.median(cycle_durations), 4)
    else:
        status = "NOT_COMPUTED"
        value = None

    explanations: list[str] = []
    if missing_status_issue_keys:
        explanations.append(
            "Median cycle time is partial because current status is missing for: "
            f"{', '.join(missing_status_issue_keys)}."
        )
    if incomplete_history_issue_keys:
        explanations.append(
            "Median cycle time is partial because Jira changelog history is incomplete for: "
            f"{', '.join(incomplete_history_issue_keys)}."
        )
    if status == "NOT_COMPUTED":
        explanations.append(
            "Median cycle time is not computed because complete evidence contains no valid "
            "in-progress-to-done transition pair."
        )

    return {
        "status": status,
        "value": value,
        "median_cycle_time_days": value,
        "available": status == "COMPUTED",
        "explanations": explanations,
        "missing_issue_keys": partial_issue_keys,
        "evidence": {
            "scoped_issue_keys": scoped_issue_keys,
            "included_issues": included_issues,
            "missing_status_issue_keys": missing_status_issue_keys,
            "incomplete_history_issue_keys": incomplete_history_issue_keys,
            "no_in_progress_issue_keys": no_in_progress_issue_keys,
            "no_later_done_issue_keys": no_later_done_issue_keys,
            "invalid_timestamp_issue_keys": invalid_timestamp_issue_keys,
        },
    }


def _evaluate_reopen_event_rate(
    issues: Sequence[Issue],
    status_histories: dict[str, list[IssueHistory]],
    field_mapper: JiraFieldMapper,
) -> dict[str, object]:
    scoped_issue_keys = sorted(issue.issue_key for issue in issues)
    missing_status_issue_keys = sorted(
        issue.issue_key for issue in issues if not _normalize_text(issue.status)
    )
    incomplete_history_issue_keys = sorted(
        issue.issue_key for issue in issues if not issue.jira_changelog_complete
    )

    reached_done_by_history: set[str] = set()
    candidate_event_identities: set[tuple[str, datetime, str, str]] = set()
    for issue_key in scoped_issue_keys:
        for history in status_histories.get(issue_key, []):
            changed_at = _coerce_utc(history.changed_at)
            old_status = _normalize_text(history.old_value)
            new_status = _normalize_text(history.new_value)
            if field_mapper.is_done_status(history.new_value):
                reached_done_by_history.add(issue_key)
            if (
                changed_at is not None
                and field_mapper.is_done_status(history.old_value)
                and bool(new_status)
                and not field_mapper.is_done_status(history.new_value)
            ):
                candidate_event_identities.add((issue_key, changed_at, old_status, new_status))

    current_done_issue_keys = {
        issue.issue_key for issue in issues if field_mapper.is_done_status(issue.status)
    }
    eligible_issue_keys = sorted(current_done_issue_keys | reached_done_by_history)
    eligible_issue_key_set = set(eligible_issue_keys)
    missing_status_affecting_issue_keys = sorted(
        set(missing_status_issue_keys) - reached_done_by_history
    )

    ordered_events = sorted(
        (
            identity
            for identity in candidate_event_identities
            if identity[0] in eligible_issue_key_set
        ),
        key=lambda item: (item[0], item[1], item[2], item[3]),
    )
    events = [
        {
            "issue_key": issue_key,
            "transition_at": changed_at.isoformat(),
            "old_status": old_status,
            "new_status": new_status,
        }
        for issue_key, changed_at, old_status, new_status in ordered_events
    ]
    event_count_by_issue: dict[str, int] = {}
    for issue_key, _changed_at, _old_status, _new_status in ordered_events:
        event_count_by_issue[issue_key] = event_count_by_issue.get(issue_key, 0) + 1
    multiple_reopen_issue_keys = sorted(
        issue_key for issue_key, count in event_count_by_issue.items() if count > 1
    )
    repeated_event_explanations = [
        f"Ticket {issue_key} was counted {event_count_by_issue[issue_key]} times because it was "
        f"reopened {event_count_by_issue[issue_key]} times."
        for issue_key in multiple_reopen_issue_keys
    ]

    partial_issue_keys = sorted(
        set(missing_status_affecting_issue_keys) | set(incomplete_history_issue_keys)
    )
    event_count = len(events)
    eligible_ticket_count = len(eligible_issue_keys)
    if partial_issue_keys:
        status = "PARTIAL"
        value = None
    elif eligible_ticket_count > 0:
        status = "COMPUTED"
        value = round(100.0 * event_count / eligible_ticket_count, 2)
    else:
        status = "NOT_COMPUTED"
        value = None

    explanations: list[str] = []
    if missing_status_affecting_issue_keys:
        explanations.append(
            "Reopen event rate is partial because current status could change eligibility for: "
            f"{', '.join(missing_status_affecting_issue_keys)}."
        )
    if incomplete_history_issue_keys:
        explanations.append(
            "Reopen event rate is partial because Jira changelog history is incomplete for: "
            f"{', '.join(incomplete_history_issue_keys)}."
        )
    if status == "NOT_COMPUTED":
        explanations.append(
            "Reopen event rate is not computed because no scoped ticket has reached done."
        )
    explanations.extend(repeated_event_explanations)

    return {
        "status": status,
        "value": value,
        "reopen_rate_pct": value,
        "available": status == "COMPUTED",
        "explanations": explanations,
        "missing_issue_keys": partial_issue_keys,
        "confirmed_eligible_ticket_count": eligible_ticket_count,
        "confirmed_reopen_event_count": event_count,
        "evidence": {
            "scoped_issue_keys": scoped_issue_keys,
            "eligible_issue_keys": eligible_issue_keys,
            "eligible_ticket_count": eligible_ticket_count,
            "reopen_events": events,
            "reopen_event_count": event_count,
            "event_count_by_issue": event_count_by_issue,
            "multiple_reopen_issue_keys": multiple_reopen_issue_keys,
            "repeated_event_explanations": repeated_event_explanations,
            "missing_status_issue_keys": missing_status_issue_keys,
            "missing_status_affecting_issue_keys": missing_status_affecting_issue_keys,
            "incomplete_history_issue_keys": incomplete_history_issue_keys,
        },
    }


def _normalize_text(value: str | None) -> str:
    return (value or "").strip().casefold()


def _valid_story_points(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    numeric_value = float(value)
    if numeric_value < 0 or not math.isfinite(numeric_value):
        return None
    return numeric_value


def _story_point_coverage(issues: list[Issue]) -> _StoryPointCoverage:
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
    normalized_snapshot_at = _coerce_utc(snapshot_at)
    assert normalized_snapshot_at is not None
    if start_at is None or end_at is None or end_at <= start_at:
        return None
    elapsed_seconds = (normalized_snapshot_at - start_at).total_seconds()
    total_seconds = (end_at - start_at).total_seconds()
    return _clamp(100.0 * elapsed_seconds / total_seconds, 0.0, 100.0)


def _score_progress_alignment(completed_scope_pct: float, time_elapsed_pct: float) -> float:
    if time_elapsed_pct <= 0:
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
) -> _ScopeStabilityInputs:
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


def _history_value_references_release(
    value: str | None,
    normalized_release_value: str,
) -> bool:
    return bool(
        normalized_release_value
        and value is not None
        and value.strip().casefold() == normalized_release_value
    )


def _issue_key_matches_project(issue_key_column, project_key: str):
    return func.upper(issue_key_column).like(f"{project_key.upper()}-%")
