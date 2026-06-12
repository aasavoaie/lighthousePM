from datetime import UTC
from datetime import datetime, timedelta
import logging
from time import perf_counter

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db.session import get_db_session
from app.repositories.metric_repository import MetricRepository
from app.repositories.release_repository import ReleaseRepository
from app.schemas.metrics import (
    ChartPoint,
    MetricThresholds,
    MetricSeries,
    MetricValues,
    MetricIssueKeys,
    RecomputeAllError,
    RecomputeAllMetricsResponse,
    RecomputeMetricsResponse,
    ReleaseChartsResponse,
    ReleaseMetricsResponse,
)
from app.schemas.deltas import (
    SnapshotBaseline,
    SnapshotChangeHistoryItem,
    SnapshotChangeHistoryResponse,
    SnapshotComparisonResponse,
    SnapshotDeltaComparison,
)
from app.services.analytics_service import AnalyticsService
from app.services.confidence_breakdown_service import ConfidenceBreakdownService
from app.services.driver_analysis_service import DriverAnalysisService
from app.services.recommendation_engine import RecommendationEngine
from app.services.signal_service import SignalService
from app.services.snapshot_comparison_service import SnapshotComparisonService
from app.utils.constants import (
    CYCLE_TIME_YELLOW_THRESHOLD_DAYS,
    HIGH_SEVERITY_BUGS_RED_THRESHOLD,
    HIGH_SEVERITY_BUGS_YELLOW_THRESHOLD,
    OPEN_BLOCKERS_RED_THRESHOLD,
    REOPEN_RATE_RED_THRESHOLD,
    REOPEN_RATE_YELLOW_THRESHOLD,
    SCOPE_CHURN_RED_THRESHOLD,
    SCOPE_CHURN_YELLOW_THRESHOLD,
)

router = APIRouter(prefix="/releases", tags=["metrics"])
logger = logging.getLogger(__name__)

METRIC_NAMES = [
    "open_blockers",
    "open_high_severity_bugs",
    "scope_completed_pct",
    "completed_tickets",
    "scope_churn_7d_pct",
    "scope_added_7d_count",
    "scope_removed_7d_count",
    "median_cycle_time_days",
    "reopen_rate_pct",
]

CHART_METRIC_NAMES = [
    *METRIC_NAMES,
    "confidence_score",
    "gates_passed_count",
    "readiness_pct",
]


def _build_metric_thresholds() -> MetricThresholds:
    return MetricThresholds(
        open_blockers_red=OPEN_BLOCKERS_RED_THRESHOLD,
        open_high_severity_bugs_red=HIGH_SEVERITY_BUGS_RED_THRESHOLD,
        open_high_severity_bugs_yellow=HIGH_SEVERITY_BUGS_YELLOW_THRESHOLD,
        scope_churn_7d_pct_red=SCOPE_CHURN_RED_THRESHOLD * 100,
        scope_churn_7d_pct_yellow=SCOPE_CHURN_YELLOW_THRESHOLD * 100,
        reopen_rate_pct_red=REOPEN_RATE_RED_THRESHOLD * 100,
        reopen_rate_pct_yellow=REOPEN_RATE_YELLOW_THRESHOLD * 100,
        median_cycle_time_days_yellow=CYCLE_TIME_YELLOW_THRESHOLD_DAYS,
    )


def _build_release_gate_values(snapshot) -> tuple[int, int, float]:
    readiness_details = SignalService._build_release_readiness_details(
        signal=None,
        open_blockers=snapshot.open_blockers,
        open_high_severity_bugs=snapshot.open_high_severity_bugs,
        scope_churn_7d_pct=snapshot.scope_churn_7d_pct,
        reopen_rate_pct=snapshot.reopen_rate_pct,
        median_cycle_time_days=snapshot.median_cycle_time_days,
    )
    gates = readiness_details.get("release_gates", [])
    total = len(gates)
    passed = sum(1 for gate in gates if isinstance(gate, dict) and gate.get("passed") is True)
    readiness_pct = 0.0 if total == 0 else round((passed / total) * 100, 2)
    return passed, total, readiness_pct


def _release_gates_total() -> int:
    class EmptySnapshot:
        open_blockers = 0
        open_high_severity_bugs = 0
        scope_churn_7d_pct = 0.0
        reopen_rate_pct = 0.0
        median_cycle_time_days = None

    _, total, _ = _build_release_gate_values(EmptySnapshot())
    return total


def _empty_snapshot_comparison(entity_id: str, baseline: SnapshotBaseline, current_snapshot_at) -> SnapshotComparisonResponse:
    return SnapshotComparisonResponse(
        entity_id=entity_id,
        baseline=baseline,
        current_snapshot_at=current_snapshot_at,
        baseline_snapshot_at=None,
        has_baseline=False,
        comparison=SnapshotDeltaComparison(confidence_delta=0.0, contributors=[]),
    )


def _select_release_baseline_snapshot(session: Session, release_id: str, current_snapshot, baseline: SnapshotBaseline):
    if baseline == "previous":
        return MetricRepository.get_previous_snapshot(
            session=session,
            release_id=release_id,
            snapshot_at=current_snapshot.snapshot_at,
            snapshot_id=current_snapshot.id,
        )
    hours = 24 if baseline == "24h" else 24 * 7
    snapshot_at = current_snapshot.snapshot_at
    if snapshot_at.tzinfo is None:
        snapshot_at = snapshot_at.replace(tzinfo=UTC)
    else:
        snapshot_at = snapshot_at.astimezone(UTC)
    return MetricRepository.get_latest_snapshot_at_or_before(
        session=session,
        release_id=release_id,
        snapshot_at=snapshot_at - timedelta(hours=hours),
    )


def _build_release_history_items(snapshots) -> list[SnapshotChangeHistoryItem]:
    items: list[SnapshotChangeHistoryItem] = []
    previous_snapshot = None
    for snapshot in snapshots:
        confidence = SignalService._confidence_score_for_snapshot(snapshot)
        if previous_snapshot is None:
            items.append(
                SnapshotChangeHistoryItem(
                    date=snapshot.snapshot_at,
                    confidence=confidence,
                    delta=None,
                    primary_driver="Baseline snapshot",
                )
            )
        else:
            comparison = SnapshotComparisonService.compare_release_snapshots(
                current_snapshot=snapshot,
                previous_snapshot=previous_snapshot,
            )
            items.append(
                SnapshotChangeHistoryItem(
                    date=snapshot.snapshot_at,
                    confidence=confidence,
                    delta=comparison.confidence_delta,
                    primary_driver=SnapshotComparisonService.primary_driver(comparison),
                )
            )
        previous_snapshot = snapshot
    return items


@router.get("/{release_id}/metrics", response_model=ReleaseMetricsResponse)
def get_release_metrics(
    release_id: str,
    session: Session = Depends(get_db_session),
) -> ReleaseMetricsResponse:
    release = ReleaseRepository.get_release_by_id(session=session, release_id=release_id)
    if release is None:
        raise HTTPException(status_code=404, detail=f"Release '{release_id}' not found")

    snapshot = MetricRepository.get_latest_snapshot(session=session, release_id=release_id)
    if snapshot is None:
        return ReleaseMetricsResponse(
            release_id=release_id,
            snapshot_at=None,
            metrics=MetricValues(
                open_blockers=None,
                open_high_severity_bugs=None,
                scope_completed_pct=None,
                completed_tickets=None,
                scope_churn_7d_pct=None,
                scope_added_7d_count=None,
                scope_removed_7d_count=None,
                median_cycle_time_days=None,
                reopen_rate_pct=None,
            ),
            metric_issue_keys=MetricIssueKeys(
                open_blockers=[],
                open_high_severity_bugs=[],
            ),
            metric_names=METRIC_NAMES,
            metric_thresholds=None,
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

    snapshot_age_hours = round(
        (datetime.now(UTC) - snapshot_at).total_seconds() / 3600.0,
        3,
    )

    return ReleaseMetricsResponse(
        release_id=release_id,
        snapshot_at=snapshot.snapshot_at,
        metrics=MetricValues(
            open_blockers=snapshot.open_blockers,
            open_high_severity_bugs=snapshot.open_high_severity_bugs,
            scope_completed_pct=snapshot.scope_completed_pct,
            completed_tickets=snapshot.completed_tickets,
            scope_churn_7d_pct=snapshot.scope_churn_7d_pct,
            scope_added_7d_count=snapshot.scope_added_7d_count,
            scope_removed_7d_count=snapshot.scope_removed_7d_count,
            median_cycle_time_days=snapshot.median_cycle_time_days,
            reopen_rate_pct=snapshot.reopen_rate_pct,
        ),
        metric_issue_keys=MetricIssueKeys(
            open_blockers=snapshot.open_blocker_issue_keys,
            open_high_severity_bugs=snapshot.open_high_severity_bug_issue_keys,
        ),
        metric_names=METRIC_NAMES,
        metric_thresholds=_build_metric_thresholds(),
        confidence_breakdown=ConfidenceBreakdownService.build_release_breakdown(snapshot),
        biggest_driver=DriverAnalysisService.build_release_driver(snapshot),
        recommendations=RecommendationEngine.build_release_recommendations(snapshot),
        is_computed=True,
        snapshot_age_hours=snapshot_age_hours,
    )


@router.get("/{release_id}/charts", response_model=ReleaseChartsResponse)
def get_release_charts(
    release_id: str,
    limit: int = Query(default=500, ge=1, le=5000),
    from_ts: datetime | None = Query(default=None, alias="from"),
    to_ts: datetime | None = Query(default=None, alias="to"),
    session: Session = Depends(get_db_session),
) -> ReleaseChartsResponse:
    release = ReleaseRepository.get_release_by_id(session=session, release_id=release_id)
    if release is None:
        raise HTTPException(status_code=404, detail=f"Release '{release_id}' not found")
    if from_ts is not None and to_ts is not None and from_ts > to_ts:
        raise HTTPException(status_code=400, detail="'from' must be less than or equal to 'to'")

    snapshots = MetricRepository.list_snapshots_for_release(
        session=session,
        release_id=release_id,
        limit=limit,
        from_at=from_ts,
        to_at=to_ts,
    )
    release_gate_values = {
        snapshot.id: _build_release_gate_values(snapshot)
        for snapshot in snapshots
    }

    return ReleaseChartsResponse(
        release_id=release_id,
        series=MetricSeries(
            open_blockers=[
                ChartPoint(snapshot_at=snapshot.snapshot_at, value=snapshot.open_blockers)
                for snapshot in snapshots
            ],
            open_high_severity_bugs=[
                ChartPoint(snapshot_at=snapshot.snapshot_at, value=snapshot.open_high_severity_bugs)
                for snapshot in snapshots
            ],
            scope_completed_pct=[
                ChartPoint(snapshot_at=snapshot.snapshot_at, value=snapshot.scope_completed_pct)
                for snapshot in snapshots
            ],
            completed_tickets=[
                ChartPoint(snapshot_at=snapshot.snapshot_at, value=snapshot.completed_tickets)
                for snapshot in snapshots
            ],
            scope_churn_7d_pct=[
                ChartPoint(snapshot_at=snapshot.snapshot_at, value=snapshot.scope_churn_7d_pct)
                for snapshot in snapshots
            ],
            scope_added_7d_count=[
                ChartPoint(snapshot_at=snapshot.snapshot_at, value=snapshot.scope_added_7d_count)
                for snapshot in snapshots
            ],
            scope_removed_7d_count=[
                ChartPoint(snapshot_at=snapshot.snapshot_at, value=snapshot.scope_removed_7d_count)
                for snapshot in snapshots
            ],
            median_cycle_time_days=[
                ChartPoint(snapshot_at=snapshot.snapshot_at, value=snapshot.median_cycle_time_days)
                for snapshot in snapshots
            ],
            reopen_rate_pct=[
                ChartPoint(snapshot_at=snapshot.snapshot_at, value=snapshot.reopen_rate_pct)
                for snapshot in snapshots
            ],
            confidence_score=[
                ChartPoint(
                    snapshot_at=snapshot.snapshot_at,
                    value=SignalService._confidence_score_for_snapshot(snapshot),
                )
                for snapshot in snapshots
            ],
            gates_passed_count=[
                ChartPoint(snapshot_at=snapshot.snapshot_at, value=release_gate_values[snapshot.id][0])
                for snapshot in snapshots
            ],
            readiness_pct=[
                ChartPoint(snapshot_at=snapshot.snapshot_at, value=release_gate_values[snapshot.id][2])
                for snapshot in snapshots
            ],
        ),
        metric_names=CHART_METRIC_NAMES,
        point_count=len(snapshots),
        release_gates_total=_release_gates_total(),
    )


@router.get("/{release_id}/snapshot-comparison", response_model=SnapshotComparisonResponse)
def get_release_snapshot_comparison(
    release_id: str,
    baseline: SnapshotBaseline = Query(default="previous"),
    session: Session = Depends(get_db_session),
) -> SnapshotComparisonResponse:
    release = ReleaseRepository.get_release_by_id(session=session, release_id=release_id)
    if release is None:
        raise HTTPException(status_code=404, detail=f"Release '{release_id}' not found")

    current_snapshot = MetricRepository.get_latest_snapshot(session=session, release_id=release_id)
    if current_snapshot is None:
        return _empty_snapshot_comparison(release_id, baseline, None)

    baseline_snapshot = _select_release_baseline_snapshot(
        session=session,
        release_id=release_id,
        current_snapshot=current_snapshot,
        baseline=baseline,
    )
    if baseline_snapshot is None:
        return _empty_snapshot_comparison(release_id, baseline, current_snapshot.snapshot_at)

    return SnapshotComparisonResponse(
        entity_id=release_id,
        baseline=baseline,
        current_snapshot_at=current_snapshot.snapshot_at,
        baseline_snapshot_at=baseline_snapshot.snapshot_at,
        has_baseline=True,
        comparison=SnapshotComparisonService.compare_release_snapshots(
            current_snapshot=current_snapshot,
            previous_snapshot=baseline_snapshot,
        ),
    )


@router.get("/{release_id}/snapshot-change-history", response_model=SnapshotChangeHistoryResponse)
def get_release_snapshot_change_history(
    release_id: str,
    limit: int = Query(default=100, ge=1, le=5000),
    session: Session = Depends(get_db_session),
) -> SnapshotChangeHistoryResponse:
    release = ReleaseRepository.get_release_by_id(session=session, release_id=release_id)
    if release is None:
        raise HTTPException(status_code=404, detail=f"Release '{release_id}' not found")

    snapshots = MetricRepository.list_snapshots_for_release(
        session=session,
        release_id=release_id,
        limit=limit,
    )
    return SnapshotChangeHistoryResponse(entity_id=release_id, items=_build_release_history_items(snapshots))


@router.post("/{release_id}/recompute", response_model=RecomputeMetricsResponse)
def recompute_release_metrics(
    release_id: str,
    session: Session = Depends(get_db_session),
) -> RecomputeMetricsResponse:
    analytics_service = AnalyticsService()
    signal_service = SignalService()
    started_at = perf_counter()
    logger.info("release_recompute_started release_id=%s", release_id)
    try:
        snapshot = analytics_service.recompute_release_metrics(session=session, release_id=release_id)
        signal_service.recompute_release_signal(session=session, release_id=release_id)
        session.commit()
        elapsed = perf_counter() - started_at
        logger.info(
            "release_recompute_completed release_id=%s elapsed_seconds=%.3f",
            release_id,
            elapsed,
        )
    except ValueError as exc:
        session.rollback()
        logger.warning("release_recompute_failed release_id=%s error=%s", release_id, exc)
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return RecomputeMetricsResponse(
        release_id=snapshot.release_id,
        snapshot_at=snapshot.snapshot_at,
        status="ok",
    )


@router.post("/recompute-all", response_model=RecomputeAllMetricsResponse)
def recompute_all_release_metrics(
    session: Session = Depends(get_db_session),
) -> RecomputeAllMetricsResponse:
    analytics_service = AnalyticsService()
    signal_service = SignalService()
    started_at = perf_counter()

    release_ids = ReleaseRepository.list_release_ids(session=session)
    errors: list[RecomputeAllError] = []
    recomputed_count = 0

    logger.info("release_recompute_all_started release_count=%d", len(release_ids))

    for release_id in release_ids:
        try:
            analytics_service.recompute_release_metrics(session=session, release_id=release_id)
            signal_service.recompute_release_signal(session=session, release_id=release_id)
            session.commit()
            recomputed_count += 1
        except Exception as exc:  # noqa: BLE001 - collect per-release errors and continue best-effort
            session.rollback()
            errors.append(RecomputeAllError(release_id=release_id, reason=str(exc)))
            logger.warning("release_recompute_all_item_failed release_id=%s error=%s", release_id, exc)

    elapsed = perf_counter() - started_at
    logger.info(
        "release_recompute_all_completed release_count=%d recomputed=%d failed=%d elapsed_seconds=%.3f",
        len(release_ids),
        recomputed_count,
        len(errors),
        elapsed,
    )

    return RecomputeAllMetricsResponse(
        releases_total=len(release_ids),
        releases_recomputed=recomputed_count,
        releases_failed=len(errors),
        elapsed_seconds=round(elapsed, 3),
        errors=errors,
    )
