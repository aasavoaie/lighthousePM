from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db_session
from app.repositories.metric_repository import MetricRepository
from app.repositories.release_repository import ReleaseRepository
from app.schemas.metrics import MetricSnapshotResponse, RecomputeMetricsResponse
from app.services.analytics_service import AnalyticsService

router = APIRouter(prefix="/releases", tags=["metrics"])


@router.get("/{release_id}/metrics", response_model=MetricSnapshotResponse)
def get_release_metrics(
    release_id: str,
    session: Session = Depends(get_db_session),
) -> MetricSnapshotResponse:
    release = ReleaseRepository.get_release_by_id(session=session, release_id=release_id)
    if release is None:
        raise HTTPException(status_code=404, detail=f"Release '{release_id}' not found")

    snapshot = MetricRepository.get_latest_snapshot(session=session, release_id=release_id)
    if snapshot is None:
        raise HTTPException(status_code=404, detail=f"No metrics found for release '{release_id}'")

    return MetricSnapshotResponse.model_validate(snapshot, from_attributes=True)


@router.post("/{release_id}/metrics/recompute", response_model=RecomputeMetricsResponse)
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
    )
