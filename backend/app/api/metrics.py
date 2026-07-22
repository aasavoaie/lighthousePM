from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db.session import get_db_session
from app.schemas.errors import ApiErrorResponse
from app.schemas.metrics import (
    RecomputeAllMetricsResponse,
    RecomputeMetricsResponse,
    ReleaseChartsResponse,
    ReleaseMetricsResponse,
)
from app.schemas.deltas import (
    SnapshotBaseline,
    SnapshotChangeHistoryResponse,
    SnapshotComparisonResponse,
)
from app.services.application_errors import (
    ApplicationNotFoundError,
    ApplicationValidationError,
)
from app.services.metric_recompute_service import MetricRecomputeService
from app.services.release_metrics_response_service import ReleaseMetricsResponseService

router = APIRouter(prefix="/releases", tags=["metrics"])


@router.get(
    "/{release_id}/metrics",
    response_model=ReleaseMetricsResponse,
    operation_id="get_release_metrics",
    summary="Get release metrics",
    responses={
        404: {
            "model": ApiErrorResponse,
            "description": "The release was not found.",
        }
    },
)
def get_release_metrics(
    release_id: str,
    session: Session = Depends(get_db_session),
) -> ReleaseMetricsResponse:
    try:
        return ReleaseMetricsResponseService().get_metrics(
            session=session,
            release_id=release_id,
            current_time=datetime.now(UTC),
        )
    except ApplicationNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get(
    "/{release_id}/charts",
    response_model=ReleaseChartsResponse,
    operation_id="get_release_charts",
    summary="Get release charts",
    responses={
        400: {
            "model": ApiErrorResponse,
            "description": "The requested chart range is invalid.",
        },
        404: {
            "model": ApiErrorResponse,
            "description": "The release was not found.",
        },
    },
)
def get_release_charts(
    release_id: str,
    limit: int = Query(default=500, ge=1, le=5000),
    from_ts: datetime | None = Query(default=None, alias="from"),
    to_ts: datetime | None = Query(default=None, alias="to"),
    session: Session = Depends(get_db_session),
) -> ReleaseChartsResponse:
    try:
        return ReleaseMetricsResponseService().get_charts(
            session=session,
            release_id=release_id,
            limit=limit,
            from_at=from_ts,
            to_at=to_ts,
        )
    except ApplicationNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ApplicationValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get(
    "/{release_id}/snapshot-comparison",
    response_model=SnapshotComparisonResponse,
    operation_id="get_release_snapshot_comparison",
    summary="Compare release snapshots",
    responses={
        404: {
            "model": ApiErrorResponse,
            "description": "The release was not found.",
        }
    },
)
def get_release_snapshot_comparison(
    release_id: str,
    baseline: SnapshotBaseline = Query(default="previous"),
    session: Session = Depends(get_db_session),
) -> SnapshotComparisonResponse:
    try:
        return ReleaseMetricsResponseService().get_snapshot_comparison(
            session=session,
            release_id=release_id,
            baseline=baseline,
        )
    except ApplicationNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get(
    "/{release_id}/snapshot-change-history",
    response_model=SnapshotChangeHistoryResponse,
    operation_id="get_release_snapshot_change_history",
    summary="Get release snapshot change history",
    responses={
        404: {
            "model": ApiErrorResponse,
            "description": "The release was not found.",
        }
    },
)
def get_release_snapshot_change_history(
    release_id: str,
    limit: int = Query(default=100, ge=1, le=5000),
    session: Session = Depends(get_db_session),
) -> SnapshotChangeHistoryResponse:
    try:
        return ReleaseMetricsResponseService().get_snapshot_change_history(
            session=session,
            release_id=release_id,
            limit=limit,
        )
    except ApplicationNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post(
    "/{release_id}/recompute",
    response_model=RecomputeMetricsResponse,
    operation_id="recompute_release_metrics",
    summary="Recompute release metrics",
    responses={
        404: {
            "model": ApiErrorResponse,
            "description": "The release was not found.",
        }
    },
)
def recompute_release_metrics(
    release_id: str,
    session: Session = Depends(get_db_session),
) -> RecomputeMetricsResponse:
    try:
        return MetricRecomputeService().recompute_release(
            session=session,
            release_id=release_id,
        )
    except ApplicationNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post(
    "/recompute-all",
    response_model=RecomputeAllMetricsResponse,
    operation_id="recompute_all_release_metrics",
    summary="Recompute all release metrics",
)
def recompute_all_release_metrics(
    session: Session = Depends(get_db_session),
) -> RecomputeAllMetricsResponse:
    return MetricRecomputeService().recompute_all_releases(session=session)
