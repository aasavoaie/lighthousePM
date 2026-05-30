from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db_session
from app.repositories.metric_repository import MetricRepository
from app.repositories.release_repository import ReleaseRepository
from app.repositories.signal_repository import SignalRepository
from app.schemas.signals import ReleaseSignalResponse, SignalReasonDetail, SignalThresholds
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

router = APIRouter(prefix="/releases", tags=["signals"])


def _build_thresholds() -> SignalThresholds:
    return SignalThresholds(
        open_blockers_red=OPEN_BLOCKERS_RED_THRESHOLD,
        open_high_severity_bugs_red=HIGH_SEVERITY_BUGS_RED_THRESHOLD,
        open_high_severity_bugs_yellow=HIGH_SEVERITY_BUGS_YELLOW_THRESHOLD,
        scope_churn_7d_pct_red=SCOPE_CHURN_RED_THRESHOLD * 100,
        scope_churn_7d_pct_yellow=SCOPE_CHURN_YELLOW_THRESHOLD * 100,
        reopen_rate_pct_red=REOPEN_RATE_RED_THRESHOLD * 100,
        reopen_rate_pct_yellow=REOPEN_RATE_YELLOW_THRESHOLD * 100,
        median_cycle_time_days_yellow=CYCLE_TIME_YELLOW_THRESHOLD_DAYS,
    )


@router.get("/{release_id}/signal", response_model=ReleaseSignalResponse)
def get_release_signal(
    release_id: str,
    session: Session = Depends(get_db_session),
) -> ReleaseSignalResponse:
    release = ReleaseRepository.get_release_by_id(session=session, release_id=release_id)
    if release is None:
        raise HTTPException(status_code=404, detail=f"Release '{release_id}' not found")

    signal_row = SignalRepository.get_latest_signal(session=session, release_id=release_id)
    if signal_row is None:
        return ReleaseSignalResponse(
            release_id=release_id,
            signal=None,
            reasons=[],
            reason_details=[],
            thresholds=_build_thresholds(),
            updated_at=None,
        )

    reason_details: list[SignalReasonDetail] = []
    latest_snapshot = MetricRepository.get_latest_snapshot(session=session, release_id=release_id)
    if latest_snapshot is not None:
        _, _, details = SignalService._evaluate_signal_with_details(
            open_blockers=latest_snapshot.open_blockers,
            open_high_severity_bugs=latest_snapshot.open_high_severity_bugs,
            scope_churn_7d_pct=latest_snapshot.scope_churn_7d_pct,
            reopen_rate_pct=latest_snapshot.reopen_rate_pct,
            median_cycle_time_days=latest_snapshot.median_cycle_time_days,
        )
        reason_details = [SignalReasonDetail.model_validate(detail) for detail in details]

    return ReleaseSignalResponse(
        release_id=signal_row.release_id,
        signal=signal_row.signal,
        reasons=signal_row.reasons,
        reason_details=reason_details,
        thresholds=_build_thresholds(),
        updated_at=signal_row.updated_at,
    )
