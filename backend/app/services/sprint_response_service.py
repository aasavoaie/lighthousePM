from datetime import UTC, datetime, timedelta
from typing import cast

from sqlalchemy.orm import Session

from app.config import get_settings
from app.metric_catalog import metric_api_fields
from app.repositories.sprint_repository import SprintRepository
from app.schemas.deltas import (
    SnapshotBaseline,
    SnapshotChangeHistoryItem,
    SnapshotChangeHistoryResponse,
    SnapshotComparisonResponse,
    SnapshotDeltaComparison,
)
from app.schemas.issues import (
    IssueResponse,
    SprintIssueListResponse,
    SprintIssueResponse,
)
from app.schemas.availability import MetricAvailabilityItem
from app.schemas.sprints import (
    CurrentSprintResponse,
    ComputationStatus,
    DeliveryConfidenceComponents,
    DeliveryConfidenceDetail,
    DeliveryConfidenceInputs,
    DeliveryConfidenceStatus,
    DeliveryConfidenceWeights,
    SprintListResponse,
    SprintMetricIssueKeys,
    SprintMetricsResponse,
    SprintMetricValues,
    SprintScopeMovementDetail,
    SprintScopeMovementEvidence,
    SprintResponse,
    StoryPointCoverage,
    WorkloadDistributionDetail,
    WorkloadDistributionEvidence,
)
from app.services.analytics_service import DELIVERY_CONFIDENCE_WEIGHTS, AnalyticsService
from app.services.application_errors import ApplicationNotFoundError
from app.services.confidence_breakdown_service import ConfidenceBreakdownService
from app.services.driver_analysis_service import DriverAnalysisService
from app.services.jira_field_mapper import JiraFieldMapper
from app.services.metric_availability_service import (
    MetricAvailabilityService,
    SPRINT_METRIC_DEPENDENCIES,
    UNAVAILABLE_REASON_SPRINT_EMPTY,
)
from app.services.recommendation_engine import RecommendationEngine
from app.services.snapshot_comparison_service import SnapshotComparisonService


SPRINT_METRIC_NAMES = list(metric_api_fields("sprint", api_location="metric_values"))
LEGACY_SCOPE_CREEP_REASON = (
    "Scope creep is unavailable because this stored snapshot does not contain "
    "an authoritative scope-creep artifact."
)


def _build_sprint_metric_availability(session: Session, sprint_id: str):
    return MetricAvailabilityService.build_sprint_availability(
        session=session,
        sprint_id=sprint_id,
        field_mapper=JiraFieldMapper(get_settings()),
    )


def _build_delivery_confidence(snapshot) -> DeliveryConfidenceDetail | None:
    if (
        snapshot.delivery_confidence_status not in {"PARTIAL", "COMPUTED"}
        or snapshot.delivery_confidence_score is None
        or snapshot.delivery_confidence_components is None
        or snapshot.delivery_confidence_inputs is None
    ):
        return None
    return DeliveryConfidenceDetail(
        score=snapshot.delivery_confidence_score,
        weights=DeliveryConfidenceWeights(**DELIVERY_CONFIDENCE_WEIGHTS),
        components=DeliveryConfidenceComponents(
            **snapshot.delivery_confidence_components
        ),
        inputs=DeliveryConfidenceInputs(**snapshot.delivery_confidence_inputs),
    )


def _build_sprint_confidence_breakdown(snapshot):
    if (
        snapshot.delivery_confidence_status not in {"PARTIAL", "COMPUTED"}
        or snapshot.delivery_confidence_score is None
        or snapshot.delivery_confidence_components is None
        or snapshot.delivery_confidence_inputs is None
    ):
        return None
    return ConfidenceBreakdownService.build_sprint_breakdown(
        score=snapshot.delivery_confidence_score,
        components=snapshot.delivery_confidence_components,
        inputs=snapshot.delivery_confidence_inputs,
    )


def _build_sprint_biggest_driver(snapshot):
    if (
        snapshot.delivery_confidence_status not in {"PARTIAL", "COMPUTED"}
        or snapshot.delivery_confidence_score is None
        or snapshot.delivery_confidence_components is None
    ):
        return None
    return DriverAnalysisService.build_sprint_driver(
        score=snapshot.delivery_confidence_score,
        components=snapshot.delivery_confidence_components,
    )


def _build_workload_distribution(snapshot):
    if (
        snapshot.workload_distribution_status is None
        or snapshot.workload_distribution_evidence is None
    ):
        return None
    return WorkloadDistributionDetail(
        status=snapshot.workload_distribution_status,
        percentage=snapshot.workload_concentration_pct,
        explanations=snapshot.workload_distribution_explanations or [],
        evidence=WorkloadDistributionEvidence.model_validate(
            snapshot.workload_distribution_evidence
        ),
    )


def _build_scope_movement(snapshot):
    if snapshot.scope_creep_evidence is None:
        return None
    return SprintScopeMovementDetail(
        status=snapshot.scope_creep_status,
        percentage=snapshot.scope_creep_pct,
        explanations=snapshot.scope_creep_explanations or [],
        evidence=SprintScopeMovementEvidence.model_validate(
            snapshot.scope_creep_evidence
        ),
    )


def _empty_snapshot_comparison(
    entity_id: str,
    baseline: SnapshotBaseline,
    current_snapshot_at,
) -> SnapshotComparisonResponse:
    return SnapshotComparisonResponse(
        entity_id=entity_id,
        baseline=baseline,
        current_snapshot_at=current_snapshot_at,
        baseline_snapshot_at=None,
        has_baseline=False,
        current_ruleset_version=None,
        baseline_ruleset_version=None,
        unavailable_reason=None,
        comparison=SnapshotDeltaComparison(confidence_delta=0.0, contributors=[]),
    )


def _unavailable_snapshot_comparison(
    entity_id: str,
    baseline: SnapshotBaseline,
    current_snapshot_at,
    baseline_snapshot_at,
    has_baseline: bool,
    current_ruleset_version: int | None = None,
    baseline_ruleset_version: int | None = None,
    unavailable_reason: str | None = None,
) -> SnapshotComparisonResponse:
    return SnapshotComparisonResponse(
        entity_id=entity_id,
        baseline=baseline,
        current_snapshot_at=current_snapshot_at,
        baseline_snapshot_at=baseline_snapshot_at,
        has_baseline=has_baseline,
        current_ruleset_version=current_ruleset_version,
        baseline_ruleset_version=baseline_ruleset_version,
        unavailable_reason=unavailable_reason,
        comparison=SnapshotDeltaComparison(confidence_delta=None, contributors=[]),
    )


def _select_sprint_baseline_snapshot(
    session: Session,
    sprint_id: str,
    current_snapshot,
    baseline: SnapshotBaseline,
):
    if baseline == "previous":
        return SprintRepository.get_previous_metric_snapshot(
            session=session,
            sprint_id=sprint_id,
            snapshot_at=current_snapshot.snapshot_at,
            snapshot_id=current_snapshot.id,
        )
    hours = 24 if baseline == "24h" else 24 * 7
    snapshot_at = current_snapshot.snapshot_at
    if snapshot_at.tzinfo is None:
        snapshot_at = snapshot_at.replace(tzinfo=UTC)
    else:
        snapshot_at = snapshot_at.astimezone(UTC)
    return SprintRepository.get_latest_metric_snapshot_at_or_before(
        session=session,
        sprint_id=sprint_id,
        snapshot_at=snapshot_at - timedelta(hours=hours),
    )


def _build_sprint_history_items(snapshots) -> list[SnapshotChangeHistoryItem]:
    items: list[SnapshotChangeHistoryItem] = []
    previous_snapshot = None
    for snapshot in snapshots:
        confidence = (
            snapshot.delivery_confidence_score
            if snapshot.delivery_confidence_status in {"PARTIAL", "COMPUTED"}
            else None
        )
        version_boundary = (
            previous_snapshot is not None
            and previous_snapshot.ruleset_version != snapshot.ruleset_version
        )
        classification_reason = (
            SnapshotComparisonService.classification_unavailable_reason(
                snapshot,
                previous_snapshot,
            )
            if previous_snapshot is not None and not version_boundary
            else None
        )
        if previous_snapshot is None:
            item = SnapshotChangeHistoryItem(
                date=snapshot.snapshot_at,
                ruleset_version=snapshot.ruleset_version,
                version_boundary=False,
                confidence=confidence,
                delta=None,
                primary_driver="Baseline snapshot"
                if confidence is not None
                else "Not available",
                comparison_unavailable_reason=None,
            )
        elif version_boundary:
            item = SnapshotChangeHistoryItem(
                date=snapshot.snapshot_at,
                ruleset_version=snapshot.ruleset_version,
                version_boundary=True,
                confidence=confidence,
                delta=None,
                primary_driver="Ruleset boundary",
                comparison_unavailable_reason=(
                    "Snapshot comparison unavailable because ruleset versions differ."
                ),
            )
        elif classification_reason is not None:
            item = SnapshotChangeHistoryItem(
                date=snapshot.snapshot_at,
                ruleset_version=snapshot.ruleset_version,
                version_boundary=False,
                confidence=confidence,
                delta=None,
                primary_driver="Classification boundary",
                comparison_unavailable_reason=classification_reason,
            )
        else:
            comparison = (
                SnapshotComparisonService.compare_sprint_snapshots(
                    current_snapshot=snapshot,
                    previous_snapshot=previous_snapshot,
                )
                if confidence is not None
                and previous_snapshot.delivery_confidence_status
                in {"PARTIAL", "COMPUTED"}
                and previous_snapshot.delivery_confidence_score is not None
                else SnapshotDeltaComparison(confidence_delta=None, contributors=[])
            )
            item = SnapshotChangeHistoryItem(
                date=snapshot.snapshot_at,
                ruleset_version=snapshot.ruleset_version,
                version_boundary=False,
                confidence=confidence,
                delta=comparison.confidence_delta,
                primary_driver=(
                    SnapshotComparisonService.primary_driver(comparison)
                    if confidence is not None
                    and previous_snapshot.delivery_confidence_status
                    in {"PARTIAL", "COMPUTED"}
                    and previous_snapshot.delivery_confidence_score is not None
                    else "Not available"
                ),
                comparison_unavailable_reason=None,
            )
        items.append(item)
        previous_snapshot = snapshot
    return items


class SprintResponseService:
    """Load sprint state and assemble the public sprint responses."""

    def list_sprints(
        self,
        *,
        session: Session,
        state: str | None,
        project_key: str | None,
        skip: int,
        limit: int,
    ) -> SprintListResponse:
        sprints, total = SprintRepository.list_sprints(
            session=session,
            state=state,
            project_key=project_key,
            skip=skip,
            limit=limit,
        )
        return SprintListResponse(
            items=[
                SprintResponse.model_validate(sprint, from_attributes=True)
                for sprint in sprints
            ],
            skip=skip,
            limit=limit,
            total=total,
        )

    def get_current_sprint(
        self,
        *,
        session: Session,
        project_key: str | None,
    ) -> CurrentSprintResponse:
        sprint = SprintRepository.get_current_sprint(
            session=session,
            project_key=project_key,
        )
        return CurrentSprintResponse(
            item=(
                SprintResponse.model_validate(sprint, from_attributes=True)
                if sprint is not None
                else None
            )
        )

    def get_sprint(self, *, session: Session, sprint_id: str) -> SprintResponse:
        sprint = SprintRepository.get_sprint_by_id(session=session, sprint_id=sprint_id)
        if sprint is None:
            raise ApplicationNotFoundError(f"Sprint '{sprint_id}' not found")
        return SprintResponse.model_validate(sprint, from_attributes=True)

    def get_sprint_issues(
        self,
        *,
        session: Session,
        sprint_id: str,
        skip: int,
        limit: int,
        current_time: datetime,
    ) -> SprintIssueListResponse:
        sprint = SprintRepository.get_sprint_by_id(session=session, sprint_id=sprint_id)
        if sprint is None:
            raise ApplicationNotFoundError(f"Sprint '{sprint_id}' not found")
        issues, total = SprintRepository.list_sprint_issues(
            session=session,
            sprint_id=sprint_id,
            skip=skip,
            limit=limit,
        )
        initial_scope_by_key = AnalyticsService().compute_sprint_initial_scope_flags(
            session=session,
            sprint=sprint,
            issue_keys=[issue.issue_key for issue in issues],
            snapshot_at=current_time,
        )
        return SprintIssueListResponse(
            items=[
                SprintIssueResponse(
                    **IssueResponse.model_validate(
                        issue, from_attributes=True
                    ).model_dump(),
                    in_initial_scope=initial_scope_by_key[issue.issue_key],
                )
                for issue in issues
            ],
            skip=skip,
            limit=limit,
            total=total,
        )

    def get_sprint_metrics(
        self,
        *,
        session: Session,
        sprint_id: str,
        current_time: datetime,
    ) -> SprintMetricsResponse:
        sprint = SprintRepository.get_sprint_by_id(session=session, sprint_id=sprint_id)
        if sprint is None:
            raise ApplicationNotFoundError(f"Sprint '{sprint_id}' not found")

        metric_availability = _build_sprint_metric_availability(
            session=session,
            sprint_id=sprint_id,
        )
        snapshot = SprintRepository.get_latest_metric_snapshot(
            session=session,
            sprint_id=sprint_id,
        )
        if snapshot is None:
            sprint_issues = SprintRepository.list_all_sprint_issues(
                session=session,
                sprint_id=sprint_id,
            )
            pointed_issues = [
                issue
                for issue in sprint_issues
                if isinstance(issue.story_points, int | float)
                and issue.story_points >= 0
            ]
            unpointed_issue_keys = sorted(
                issue.issue_key
                for issue in sprint_issues
                if issue not in pointed_issues
            )
            coverage_pct = (
                round(100.0 * len(pointed_issues) / len(sprint_issues), 2)
                if sprint_issues
                else 0.0
            )
            computation_status, unavailable_reason = (
                MetricAvailabilityService.computation_state(
                    metric_availability,
                    is_computed=False,
                    empty_scope_reason=UNAVAILABLE_REASON_SPRINT_EMPTY,
                )
            )
            return SprintMetricsResponse(
                sprint_id=sprint_id,
                ruleset_version=None,
                ruleset_label=None,
                calculation_provenance=None,
                snapshot_at=None,
                computation_status=computation_status,
                unavailable_reason=unavailable_reason,
                metrics=SprintMetricValues(
                    committed_scope=None,
                    completed_scope_pct=None,
                    scope_creep_pct=None,
                    open_blockers=None,
                    open_high_severity_bugs=None,
                    bugs_created_during_sprint=None,
                    in_progress_count=None,
                    not_started_count=None,
                    rollover_count=None,
                    median_cycle_time_days=None,
                    reopen_rate_pct=None,
                    workload_concentration_pct=None,
                    delivery_confidence_score=None,
                ),
                metric_issue_keys=SprintMetricIssueKeys(
                    open_blockers=[],
                    open_high_severity_bugs=[],
                    bugs_created_during_sprint=[],
                    bugs_created_during_sprint_missing_created_at=[],
                ),
                bugs_created_during_sprint_status="NOT_COMPUTED",
                metric_names=SPRINT_METRIC_NAMES,
                metric_availability=metric_availability,
                story_point_coverage=StoryPointCoverage(
                    total_ticket_count=len(sprint_issues),
                    pointed_ticket_count=len(pointed_issues),
                    unpointed_ticket_count=len(unpointed_issue_keys),
                    coverage_pct=coverage_pct,
                    unpointed_issue_keys=unpointed_issue_keys,
                ),
                delivery_confidence_status="NOT_COMPUTED",
                delivery_confidence_explanations=[
                    "Delivery confidence has not been computed for this sprint snapshot."
                ],
                delivery_confidence=None,
                scope_movement=None,
                workload_distribution=None,
                confidence_breakdown=None,
                biggest_driver=None,
                recommendations=[],
                is_computed=False,
                snapshot_age_hours=None,
            )

        snapshot_at = snapshot.snapshot_at
        if snapshot_at.tzinfo is None:
            snapshot_at = snapshot_at.replace(tzinfo=UTC)
        else:
            snapshot_at = snapshot_at.astimezone(UTC)
        normalized_current_time = current_time
        if normalized_current_time.tzinfo is None:
            normalized_current_time = normalized_current_time.replace(tzinfo=UTC)
        else:
            normalized_current_time = normalized_current_time.astimezone(UTC)

        provenance = snapshot.calculation_provenance or {}
        stored_availability = provenance.get("availability")
        if snapshot.ruleset_version > 0 and isinstance(stored_availability, dict):
            metric_availability = type(metric_availability).model_validate(
                stored_availability
            )
        if "scope_creep_pct" not in metric_availability.metrics:
            metric_availability.metrics["scope_creep_pct"] = MetricAvailabilityItem(
                status="NOT_COMPUTED",
                available=False,
                reason=LEGACY_SCOPE_CREEP_REASON,
                explanations=[LEGACY_SCOPE_CREEP_REASON],
                missing_issue_keys=[],
                depends_on=SPRINT_METRIC_DEPENDENCIES["scope_creep_pct"],
            )
        has_delivery_confidence = (
            snapshot.delivery_confidence_status in {"PARTIAL", "COMPUTED"}
            and snapshot.delivery_confidence_score is not None
        )
        computation_status, unavailable_reason = (
            MetricAvailabilityService.computation_state(
                metric_availability,
                is_computed=True,
                empty_scope_reason=UNAVAILABLE_REASON_SPRINT_EMPTY,
            )
        )
        if snapshot.ruleset_version > 0:
            stored_computation_status = provenance.get("computation_status")
            if stored_computation_status in {
                "COMPUTED",
                "PARTIAL",
                "NOT_COMPUTED",
            }:
                computation_status = cast(
                    ComputationStatus,
                    stored_computation_status,
                )
            if "unavailable_reason" in provenance:
                stored_unavailable_reason = provenance["unavailable_reason"]
                if stored_unavailable_reason is None or isinstance(
                    stored_unavailable_reason,
                    str,
                ):
                    unavailable_reason = stored_unavailable_reason

        component_outputs = provenance.get("component_outputs", {})
        if not isinstance(component_outputs, dict):
            component_outputs = {}

        return SprintMetricsResponse(
            sprint_id=sprint_id,
            ruleset_version=snapshot.ruleset_version,
            ruleset_label=(
                "Unversioned legacy result"
                if snapshot.ruleset_version == 0
                else f"Ruleset v{snapshot.ruleset_version}"
            ),
            calculation_provenance=provenance,
            snapshot_at=snapshot.snapshot_at,
            computation_status=computation_status,
            unavailable_reason=unavailable_reason,
            metrics=SprintMetricValues(
                committed_scope=snapshot.committed_scope,
                completed_scope_pct=snapshot.completed_scope_pct,
                scope_creep_pct=(
                    snapshot.scope_creep_pct
                    if metric_availability.metrics["scope_creep_pct"].available
                    else None
                ),
                open_blockers=(
                    snapshot.open_blockers
                    if metric_availability.metrics["open_blockers"].available
                    else None
                ),
                open_high_severity_bugs=(
                    snapshot.open_high_severity_bugs
                    if metric_availability.metrics["open_high_severity_bugs"].available
                    else None
                ),
                bugs_created_during_sprint=(
                    snapshot.bugs_created_during_sprint
                    if snapshot.bugs_created_during_sprint_status != "NOT_COMPUTED"
                    else None
                ),
                in_progress_count=(
                    snapshot.in_progress_count
                    if metric_availability.metrics["in_progress_count"].available
                    else None
                ),
                not_started_count=(
                    snapshot.not_started_count
                    if metric_availability.metrics["not_started_count"].available
                    else None
                ),
                rollover_count=(
                    snapshot.rollover_count
                    if metric_availability.metrics["rollover_count"].available
                    else None
                ),
                median_cycle_time_days=snapshot.median_cycle_time_days,
                reopen_rate_pct=snapshot.reopen_rate_pct,
                workload_concentration_pct=(
                    snapshot.workload_concentration_pct
                    if (
                        (
                            workload_availability := metric_availability.metrics.get(
                                "workload_concentration_pct"
                            )
                        )
                        and workload_availability.available
                    )
                    else None
                ),
                delivery_confidence_score=(
                    snapshot.delivery_confidence_score
                    if has_delivery_confidence
                    else None
                ),
            ),
            metric_issue_keys=SprintMetricIssueKeys(
                open_blockers=snapshot.open_blocker_issue_keys,
                open_high_severity_bugs=snapshot.open_high_severity_bug_issue_keys,
                bugs_created_during_sprint=snapshot.bugs_created_during_sprint_issue_keys,
                bugs_created_during_sprint_missing_created_at=(
                    snapshot.bugs_created_during_sprint_missing_created_at_issue_keys
                ),
            ),
            bugs_created_during_sprint_status=cast(
                ComputationStatus,
                snapshot.bugs_created_during_sprint_status,
            ),
            metric_names=SPRINT_METRIC_NAMES,
            metric_availability=metric_availability,
            story_point_coverage=StoryPointCoverage(
                total_ticket_count=snapshot.story_point_total_count,
                pointed_ticket_count=snapshot.story_point_pointed_count,
                unpointed_ticket_count=snapshot.story_point_unpointed_count,
                coverage_pct=snapshot.story_point_coverage_pct,
                unpointed_issue_keys=snapshot.story_point_unpointed_issue_keys,
            ),
            delivery_confidence_status=cast(
                DeliveryConfidenceStatus,
                snapshot.delivery_confidence_status,
            ),
            delivery_confidence_explanations=snapshot.delivery_confidence_explanations,
            delivery_confidence=_build_delivery_confidence(snapshot),
            scope_movement=_build_scope_movement(snapshot),
            workload_distribution=_build_workload_distribution(snapshot),
            confidence_breakdown=(
                component_outputs.get("confidence_breakdown")
                if snapshot.ruleset_version > 0
                else _build_sprint_confidence_breakdown(snapshot)
            ),
            biggest_driver=(
                component_outputs.get("biggest_driver")
                if snapshot.ruleset_version > 0
                else _build_sprint_biggest_driver(snapshot)
            ),
            recommendations=RecommendationEngine.build_sprint_recommendations(
                snapshot,
                include_story_point_rules=has_delivery_confidence,
            ),
            is_computed=True,
            snapshot_age_hours=round(
                (normalized_current_time - snapshot_at).total_seconds() / 3600.0,
                3,
            ),
        )

    def get_snapshot_comparison(
        self,
        *,
        session: Session,
        sprint_id: str,
        baseline: SnapshotBaseline,
    ) -> SnapshotComparisonResponse:
        sprint = SprintRepository.get_sprint_by_id(session=session, sprint_id=sprint_id)
        if sprint is None:
            raise ApplicationNotFoundError(f"Sprint '{sprint_id}' not found")
        current_snapshot = SprintRepository.get_latest_metric_snapshot(
            session=session,
            sprint_id=sprint_id,
        )
        if current_snapshot is None:
            return _empty_snapshot_comparison(sprint_id, baseline, None)
        baseline_snapshot = _select_sprint_baseline_snapshot(
            session=session,
            sprint_id=sprint_id,
            current_snapshot=current_snapshot,
            baseline=baseline,
        )
        if (
            baseline_snapshot is not None
            and current_snapshot.ruleset_version != baseline_snapshot.ruleset_version
        ):
            return _unavailable_snapshot_comparison(
                entity_id=sprint_id,
                baseline=baseline,
                current_snapshot_at=current_snapshot.snapshot_at,
                baseline_snapshot_at=baseline_snapshot.snapshot_at,
                has_baseline=True,
                current_ruleset_version=current_snapshot.ruleset_version,
                baseline_ruleset_version=baseline_snapshot.ruleset_version,
                unavailable_reason=(
                    "Snapshot comparison unavailable because ruleset versions differ."
                ),
            )
        if (
            current_snapshot.delivery_confidence_status not in {"PARTIAL", "COMPUTED"}
            or current_snapshot.delivery_confidence_score is None
            or (
                baseline_snapshot is not None
                and (
                    baseline_snapshot.delivery_confidence_status
                    not in {"PARTIAL", "COMPUTED"}
                    or baseline_snapshot.delivery_confidence_score is None
                )
            )
        ):
            return _unavailable_snapshot_comparison(
                entity_id=sprint_id,
                baseline=baseline,
                current_snapshot_at=current_snapshot.snapshot_at,
                baseline_snapshot_at=(
                    baseline_snapshot.snapshot_at
                    if baseline_snapshot is not None
                    else None
                ),
                has_baseline=baseline_snapshot is not None,
                current_ruleset_version=current_snapshot.ruleset_version,
                baseline_ruleset_version=(
                    baseline_snapshot.ruleset_version
                    if baseline_snapshot is not None
                    else None
                ),
                unavailable_reason="Delivery confidence is unavailable for one or both snapshots.",
            )
        if baseline_snapshot is None:
            response = _empty_snapshot_comparison(
                sprint_id,
                baseline,
                current_snapshot.snapshot_at,
            )
            response.current_ruleset_version = current_snapshot.ruleset_version
            return response
        classification_reason = (
            SnapshotComparisonService.classification_unavailable_reason(
                current_snapshot,
                baseline_snapshot,
            )
        )
        if classification_reason is not None:
            return _unavailable_snapshot_comparison(
                entity_id=sprint_id,
                baseline=baseline,
                current_snapshot_at=current_snapshot.snapshot_at,
                baseline_snapshot_at=baseline_snapshot.snapshot_at,
                has_baseline=True,
                current_ruleset_version=current_snapshot.ruleset_version,
                baseline_ruleset_version=baseline_snapshot.ruleset_version,
                unavailable_reason=classification_reason,
            )
        return SnapshotComparisonResponse(
            entity_id=sprint_id,
            baseline=baseline,
            current_snapshot_at=current_snapshot.snapshot_at,
            baseline_snapshot_at=baseline_snapshot.snapshot_at,
            has_baseline=True,
            current_ruleset_version=current_snapshot.ruleset_version,
            baseline_ruleset_version=baseline_snapshot.ruleset_version,
            unavailable_reason=None,
            comparison=SnapshotComparisonService.compare_sprint_snapshots(
                current_snapshot=current_snapshot,
                previous_snapshot=baseline_snapshot,
            ),
        )

    def get_snapshot_change_history(
        self,
        *,
        session: Session,
        sprint_id: str,
        limit: int,
    ) -> SnapshotChangeHistoryResponse:
        sprint = SprintRepository.get_sprint_by_id(session=session, sprint_id=sprint_id)
        if sprint is None:
            raise ApplicationNotFoundError(f"Sprint '{sprint_id}' not found")
        snapshots = SprintRepository.list_metric_snapshots_for_sprint(
            session=session,
            sprint_id=sprint_id,
            limit=limit,
        )
        return SnapshotChangeHistoryResponse(
            entity_id=sprint_id,
            items=_build_sprint_history_items(snapshots),
        )
