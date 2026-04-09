from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db.session import get_db_session
from app.repositories.metric_repository import MetricRepository
from app.repositories.release_repository import ReleaseRepository
from app.schemas.metrics import (
    ChartPoint,
    MetricSeries,
    MetricValues,
    RecomputeMetricsResponse,
    ReleaseChartsResponse,
    ReleaseMetricsResponse,
)
from app.services.analytics_service import AnalyticsService

router = APIRouter(prefix="/releases", tags=["metrics"])


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
                scope_churn_7d_pct=None,
                median_cycle_time_days=None,
                reopen_rate_pct=None,
            ),
        )

    return ReleaseMetricsResponse(
        release_id=release_id,
        snapshot_at=snapshot.snapshot_at,
        metrics=MetricValues(
            open_blockers=snapshot.open_blockers,
            open_high_severity_bugs=snapshot.open_high_severity_bugs,
            scope_completed_pct=snapshot.scope_completed_pct,
            scope_churn_7d_pct=snapshot.scope_churn_7d_pct,
            median_cycle_time_days=snapshot.median_cycle_time_days,
            reopen_rate_pct=snapshot.reopen_rate_pct,
        ),
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
            scope_churn_7d_pct=[
                ChartPoint(snapshot_at=snapshot.snapshot_at, value=snapshot.scope_churn_7d_pct)
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
        ),
    )


@router.post("/{release_id}/recompute", response_model=RecomputeMetricsResponse)
def recompute_release_metrics(
    release_id: str,
    session: Session = Depends(get_db_session),
) -> RecomputeMetricsResponse:
    service = AnalyticsService()
    try:
        snapshot = service.recompute_release_metrics(session=session, release_id=release_id)
        session.commit()
    except ValueError as exc:
        session.rollback()
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return RecomputeMetricsResponse(
        release_id=snapshot.release_id,
        snapshot_at=snapshot.snapshot_at,
        status="ok",
    )
