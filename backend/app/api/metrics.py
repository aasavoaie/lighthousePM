from datetime import datetime
from datetime import UTC
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
from app.services.analytics_service import AnalyticsService
from app.services.signal_service import SignalService
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
