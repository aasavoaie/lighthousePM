from datetime import UTC, datetime, timedelta
from time import perf_counter

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.session import get_db_session
from app.repositories.sprint_repository import SprintRepository
from app.schemas.issues import IssueResponse, SprintIssueListResponse, SprintIssueResponse
from app.schemas.deltas import (
    SnapshotBaseline,
    SnapshotChangeHistoryItem,
    SnapshotChangeHistoryResponse,
    SnapshotComparisonResponse,
    SnapshotDeltaComparison,
)
from app.schemas.sprints import (
    CurrentSprintResponse,
    DeliveryConfidenceComponents,
    DeliveryConfidenceDetail,
    DeliveryConfidenceInputs,
    DeliveryConfidenceWeights,
    RecomputeSprintMetricsResponse,
    SprintListResponse,
    SprintMetricIssueKeys,
    SprintMetricsResponse,
    SprintMetricValues,
    SprintResponse,
)
from app.services.analytics_service import DELIVERY_CONFIDENCE_WEIGHTS, AnalyticsService
from app.services.confidence_breakdown_service import ConfidenceBreakdownService
from app.services.driver_analysis_service import DriverAnalysisService
from app.services.jira_field_mapper import JiraFieldMapper
from app.services.metric_availability_service import (
    MetricAvailabilityService,
    UNAVAILABLE_REASON_SPRINT_EMPTY,
)
from app.services.recommendation_engine import RecommendationEngine
from app.services.snapshot_comparison_service import SnapshotComparisonService

router = APIRouter(prefix="/sprints", tags=["sprints"])

SPRINT_METRIC_NAMES = [
    "committed_scope",
    "completed_scope_pct",
    "open_blockers",
    "open_high_severity_bugs",
    "bugs_created_during_sprint",
    "in_progress_count",
    "not_started_count",
    "rollover_count",
    "median_cycle_time_days",
    "reopen_rate_pct",
    "delivery_confidence_score",
]


def _build_sprint_metric_availability(session: Session, sprint_id: str):
    field_mapper = JiraFieldMapper(get_settings())
    return MetricAvailabilityService.build_sprint_availability(
        session=session,
        sprint_id=sprint_id,
        field_mapper=field_mapper,
    )


def _build_delivery_confidence(snapshot) -> DeliveryConfidenceDetail | None:
    if (
        snapshot.delivery_confidence_score is None
        or snapshot.delivery_confidence_components is None
        or snapshot.delivery_confidence_inputs is None
    ):
        return None
    return DeliveryConfidenceDetail(
        score=snapshot.delivery_confidence_score,
        weights=DeliveryConfidenceWeights(**DELIVERY_CONFIDENCE_WEIGHTS),
        components=DeliveryConfidenceComponents(**snapshot.delivery_confidence_components),
        inputs=DeliveryConfidenceInputs(**snapshot.delivery_confidence_inputs),
    )


def _build_sprint_confidence_breakdown(snapshot):
    if (
        snapshot.delivery_confidence_score is None
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
    if snapshot.delivery_confidence_score is None or snapshot.delivery_confidence_components is None:
        return None
    return DriverAnalysisService.build_sprint_driver(
        score=snapshot.delivery_confidence_score,
        components=snapshot.delivery_confidence_components,
    )


def _empty_snapshot_comparison(entity_id: str, baseline: SnapshotBaseline, current_snapshot_at) -> SnapshotComparisonResponse:
    return SnapshotComparisonResponse(
        entity_id=entity_id,
        baseline=baseline,
        current_snapshot_at=current_snapshot_at,
        baseline_snapshot_at=None,
        has_baseline=False,
        comparison=SnapshotDeltaComparison(confidence_delta=0.0, contributors=[]),
    )


def _unavailable_snapshot_comparison(
    entity_id: str,
    baseline: SnapshotBaseline,
    current_snapshot_at,
    baseline_snapshot_at,
    has_baseline: bool,
) -> SnapshotComparisonResponse:
    return SnapshotComparisonResponse(
        entity_id=entity_id,
        baseline=baseline,
        current_snapshot_at=current_snapshot_at,
        baseline_snapshot_at=baseline_snapshot_at,
        has_baseline=has_baseline,
        comparison=SnapshotDeltaComparison(confidence_delta=None, contributors=[]),
    )


def _select_sprint_baseline_snapshot(session: Session, sprint_id: str, current_snapshot, baseline: SnapshotBaseline):
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


def _build_sprint_history_items(snapshots, has_story_points: bool = True) -> list[SnapshotChangeHistoryItem]:
    items: list[SnapshotChangeHistoryItem] = []
    previous_snapshot = None
    for snapshot in snapshots:
        confidence = snapshot.delivery_confidence_score if has_story_points else None
        if previous_snapshot is None:
            items.append(
                SnapshotChangeHistoryItem(
                    date=snapshot.snapshot_at,
                    confidence=confidence,
                    delta=None,
                    primary_driver="Baseline snapshot" if has_story_points else "Not available",
                )
            )
        else:
            comparison = (
                SnapshotComparisonService.compare_sprint_snapshots(
                    current_snapshot=snapshot,
                    previous_snapshot=previous_snapshot,
                )
                if has_story_points
                else SnapshotDeltaComparison(confidence_delta=None, contributors=[])
            )
            items.append(
                SnapshotChangeHistoryItem(
                    date=snapshot.snapshot_at,
                    confidence=confidence,
                    delta=comparison.confidence_delta,
                    primary_driver=(
                        SnapshotComparisonService.primary_driver(comparison)
                        if has_story_points
                        else "Not available"
                    ),
                )
            )
        previous_snapshot = snapshot
    return items


@router.get("", response_model=SprintListResponse)
def get_sprints(
    state: str | None = Query(default=None, pattern="^(active|closed|future)$"),
    project_key: str | None = Query(default=None, min_length=1),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=100),
    session: Session = Depends(get_db_session),
) -> SprintListResponse:
    sprints, total = SprintRepository.list_sprints(
        session=session,
        state=state,
        project_key=project_key,
        skip=skip,
        limit=limit,
    )
    return SprintListResponse(
        items=[SprintResponse.model_validate(sprint, from_attributes=True) for sprint in sprints],
        skip=skip,
        limit=limit,
        total=total,
    )


@router.get("/current", response_model=CurrentSprintResponse)
def get_current_sprint(
    project_key: str | None = Query(default=None, min_length=1),
    session: Session = Depends(get_db_session),
) -> CurrentSprintResponse:
    sprint = SprintRepository.get_current_sprint(session=session, project_key=project_key)
    if sprint is None:
        return CurrentSprintResponse(item=None)
    return CurrentSprintResponse(item=SprintResponse.model_validate(sprint, from_attributes=True))


@router.get("/{sprint_id}", response_model=SprintResponse)
def get_sprint(sprint_id: str, session: Session = Depends(get_db_session)) -> SprintResponse:
    sprint = SprintRepository.get_sprint_by_id(session=session, sprint_id=sprint_id)
    if sprint is None:
        raise HTTPException(status_code=404, detail=f"Sprint '{sprint_id}' not found")
    return SprintResponse.model_validate(sprint, from_attributes=True)


@router.get("/{sprint_id}/issues", response_model=SprintIssueListResponse)
def get_sprint_issues(
    sprint_id: str,
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=100),
    session: Session = Depends(get_db_session),
) -> SprintIssueListResponse:
    sprint = SprintRepository.get_sprint_by_id(session=session, sprint_id=sprint_id)
    if sprint is None:
        raise HTTPException(status_code=404, detail=f"Sprint '{sprint_id}' not found")

    issues, total = SprintRepository.list_sprint_issues(session=session, sprint_id=sprint_id, skip=skip, limit=limit)
    initial_scope_by_key = AnalyticsService().compute_sprint_initial_scope_flags(
        session=session,
        sprint=sprint,
        issue_keys=[issue.issue_key for issue in issues],
        snapshot_at=datetime.now(UTC),
    )
    return SprintIssueListResponse(
        items=[
            SprintIssueResponse(
                **IssueResponse.model_validate(issue, from_attributes=True).model_dump(),
                in_initial_scope=initial_scope_by_key[issue.issue_key],
            )
            for issue in issues
        ],
        skip=skip,
        limit=limit,
        total=total,
    )


@router.get("/{sprint_id}/metrics", response_model=SprintMetricsResponse)
def get_sprint_metrics(
    sprint_id: str,
    session: Session = Depends(get_db_session),
) -> SprintMetricsResponse:
    sprint = SprintRepository.get_sprint_by_id(session=session, sprint_id=sprint_id)
    if sprint is None:
        raise HTTPException(status_code=404, detail=f"Sprint '{sprint_id}' not found")

    metric_availability = _build_sprint_metric_availability(session=session, sprint_id=sprint_id)
    snapshot = SprintRepository.get_latest_metric_snapshot(session=session, sprint_id=sprint_id)
    if snapshot is None:
        computation_status, unavailable_reason = MetricAvailabilityService.computation_state(
            metric_availability,
            is_computed=False,
            empty_scope_reason=UNAVAILABLE_REASON_SPRINT_EMPTY,
        )
        return SprintMetricsResponse(
            sprint_id=sprint_id,
            snapshot_at=None,
            computation_status=computation_status,
            unavailable_reason=unavailable_reason,
            metrics=SprintMetricValues(
                committed_scope=None,
                completed_scope_pct=None,
                open_blockers=None,
                open_high_severity_bugs=None,
                bugs_created_during_sprint=None,
                in_progress_count=None,
                not_started_count=None,
                rollover_count=None,
                median_cycle_time_days=None,
                reopen_rate_pct=None,
                delivery_confidence_score=None,
            ),
            metric_issue_keys=SprintMetricIssueKeys(
                open_blockers=[],
                open_high_severity_bugs=[],
                bugs_created_during_sprint=[],
            ),
            metric_names=SPRINT_METRIC_NAMES,
            metric_availability=metric_availability,
            delivery_confidence=None,
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
    sprint_issues = SprintRepository.list_all_sprint_issues(session=session, sprint_id=sprint_id)
    has_story_points = metric_availability.context.has_story_points
    delivery_confidence_score = snapshot.delivery_confidence_score if has_story_points else None
    computation_status, unavailable_reason = MetricAvailabilityService.computation_state(
        metric_availability,
        is_computed=True,
        empty_scope_reason=UNAVAILABLE_REASON_SPRINT_EMPTY,
    )

    return SprintMetricsResponse(
        sprint_id=sprint_id,
        snapshot_at=snapshot.snapshot_at,
        computation_status=computation_status,
        unavailable_reason=unavailable_reason,
        metrics=SprintMetricValues(
            committed_scope=snapshot.committed_scope,
            completed_scope_pct=snapshot.completed_scope_pct,
            open_blockers=snapshot.open_blockers,
            open_high_severity_bugs=snapshot.open_high_severity_bugs,
            bugs_created_during_sprint=snapshot.bugs_created_during_sprint,
            in_progress_count=snapshot.in_progress_count,
            not_started_count=snapshot.not_started_count,
            rollover_count=snapshot.rollover_count,
            median_cycle_time_days=snapshot.median_cycle_time_days,
            reopen_rate_pct=snapshot.reopen_rate_pct,
            delivery_confidence_score=delivery_confidence_score,
        ),
        metric_issue_keys=SprintMetricIssueKeys(
            open_blockers=snapshot.open_blocker_issue_keys,
            open_high_severity_bugs=snapshot.open_high_severity_bug_issue_keys,
            bugs_created_during_sprint=snapshot.bugs_created_during_sprint_issue_keys,
        ),
        metric_names=SPRINT_METRIC_NAMES,
        metric_availability=metric_availability,
        delivery_confidence=_build_delivery_confidence(snapshot) if has_story_points else None,
        confidence_breakdown=_build_sprint_confidence_breakdown(snapshot) if has_story_points else None,
        biggest_driver=_build_sprint_biggest_driver(snapshot) if has_story_points else None,
        recommendations=RecommendationEngine.build_sprint_recommendations(
            snapshot,
            sprint_issues=sprint_issues,
            include_story_point_rules=has_story_points,
        ),
        is_computed=True,
        snapshot_age_hours=round((datetime.now(UTC) - snapshot_at).total_seconds() / 3600.0, 3),
    )


@router.get("/{sprint_id}/snapshot-comparison", response_model=SnapshotComparisonResponse)
def get_sprint_snapshot_comparison(
    sprint_id: str,
    baseline: SnapshotBaseline = Query(default="previous"),
    session: Session = Depends(get_db_session),
) -> SnapshotComparisonResponse:
    sprint = SprintRepository.get_sprint_by_id(session=session, sprint_id=sprint_id)
    if sprint is None:
        raise HTTPException(status_code=404, detail=f"Sprint '{sprint_id}' not found")

    current_snapshot = SprintRepository.get_latest_metric_snapshot(session=session, sprint_id=sprint_id)
    if current_snapshot is None:
        return _empty_snapshot_comparison(sprint_id, baseline, None)

    metric_availability = _build_sprint_metric_availability(session=session, sprint_id=sprint_id)
    baseline_snapshot = _select_sprint_baseline_snapshot(
        session=session,
        sprint_id=sprint_id,
        current_snapshot=current_snapshot,
        baseline=baseline,
    )
    if not metric_availability.context.has_story_points:
        return _unavailable_snapshot_comparison(
            entity_id=sprint_id,
            baseline=baseline,
            current_snapshot_at=current_snapshot.snapshot_at,
            baseline_snapshot_at=baseline_snapshot.snapshot_at if baseline_snapshot is not None else None,
            has_baseline=baseline_snapshot is not None,
        )
    if baseline_snapshot is None:
        return _empty_snapshot_comparison(sprint_id, baseline, current_snapshot.snapshot_at)

    return SnapshotComparisonResponse(
        entity_id=sprint_id,
        baseline=baseline,
        current_snapshot_at=current_snapshot.snapshot_at,
        baseline_snapshot_at=baseline_snapshot.snapshot_at,
        has_baseline=True,
        comparison=SnapshotComparisonService.compare_sprint_snapshots(
            current_snapshot=current_snapshot,
            previous_snapshot=baseline_snapshot,
        ),
    )


@router.get("/{sprint_id}/snapshot-change-history", response_model=SnapshotChangeHistoryResponse)
def get_sprint_snapshot_change_history(
    sprint_id: str,
    limit: int = Query(default=100, ge=1, le=5000),
    session: Session = Depends(get_db_session),
) -> SnapshotChangeHistoryResponse:
    sprint = SprintRepository.get_sprint_by_id(session=session, sprint_id=sprint_id)
    if sprint is None:
        raise HTTPException(status_code=404, detail=f"Sprint '{sprint_id}' not found")

    snapshots = SprintRepository.list_metric_snapshots_for_sprint(
        session=session,
        sprint_id=sprint_id,
        limit=limit,
    )
    metric_availability = _build_sprint_metric_availability(session=session, sprint_id=sprint_id)
    return SnapshotChangeHistoryResponse(
        entity_id=sprint_id,
        items=_build_sprint_history_items(
            snapshots,
            has_story_points=metric_availability.context.has_story_points,
        ),
    )


@router.post("/{sprint_id}/recompute", response_model=RecomputeSprintMetricsResponse)
def recompute_sprint_metrics(
    sprint_id: str,
    session: Session = Depends(get_db_session),
) -> RecomputeSprintMetricsResponse:
    started_at = perf_counter()
    try:
        snapshot = AnalyticsService().recompute_sprint_metrics(session=session, sprint_id=sprint_id)
        session.commit()
    except ValueError as exc:
        session.rollback()
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    _ = perf_counter() - started_at
    return RecomputeSprintMetricsResponse(
        sprint_id=snapshot.sprint_id,
        snapshot_at=snapshot.snapshot_at,
        status="ok",
    )
