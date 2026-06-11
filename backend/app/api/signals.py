from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db_session
from app.repositories.metric_repository import MetricRepository
from app.repositories.release_repository import ReleaseRepository
from app.repositories.signal_repository import SignalRepository
from app.schemas.signals import ReleaseSignalResponse, SignalReasonDetail, SignalThresholds
from app.services.signal_service import SignalService
from app.utils.constants import (
    CONFIDENCE_SCORE_GREEN_MIN,
    CONFIDENCE_SCORE_RED_MAX,
    CONFIDENCE_SCORE_YELLOW_MAX,
    CONFIDENCE_SCORE_YELLOW_MIN,
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


def _empty_risk_aging() -> dict[str, object]:
    empty_group = {"count": 0, "oldest_age_days": None, "average_age_days": None, "tickets": []}
    return {"blockers": empty_group, "high_severity_bugs": empty_group, "as_of": None}


def _empty_last_24_hours() -> dict[str, object]:
    return {"as_of": None, "baseline_at": None, "has_baseline": False, "items": []}


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
        confidence_score_red_max=CONFIDENCE_SCORE_RED_MAX,
        confidence_score_yellow_min=CONFIDENCE_SCORE_YELLOW_MIN,
        confidence_score_yellow_max=CONFIDENCE_SCORE_YELLOW_MAX,
        confidence_score_green_min=CONFIDENCE_SCORE_GREEN_MIN,
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
            status_label="NOT COMPUTED",
            confidence_score=None,
            summary="Signal has not been computed yet for this release snapshot.",
            reasons=[],
            reason_details=[],
            risk_aging=_empty_risk_aging(),
            last_24_hours=_empty_last_24_hours(),
            thresholds=_build_thresholds(),
            updated_at=None,
        )

    reason_details: list[SignalReasonDetail] = []
    readiness_details: dict[str, object] = {}
    risk_aging: dict[str, object] = _empty_risk_aging()
    last_24_hours: dict[str, object] = _empty_last_24_hours()
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
        readiness_details = SignalService._build_release_readiness_details(
            signal=signal_row.signal,
            open_blockers=latest_snapshot.open_blockers,
            open_high_severity_bugs=latest_snapshot.open_high_severity_bugs,
            scope_churn_7d_pct=latest_snapshot.scope_churn_7d_pct,
            reopen_rate_pct=latest_snapshot.reopen_rate_pct,
            median_cycle_time_days=latest_snapshot.median_cycle_time_days,
        )
        risk_aging = SignalService._build_release_risk_aging(
            session=session,
            release_id=release_id,
            as_of=latest_snapshot.snapshot_at,
            open_blocker_issue_keys=(
                latest_snapshot.open_blocker_issue_keys
                if latest_snapshot.open_blocker_issue_keys or latest_snapshot.open_blockers == 0
                else None
            ),
            open_high_severity_bug_issue_keys=(
                latest_snapshot.open_high_severity_bug_issue_keys
                if latest_snapshot.open_high_severity_bug_issue_keys or latest_snapshot.open_high_severity_bugs == 0
                else None
            ),
        )
        last_24_hours = SignalService._build_last_24_hours(
            session=session,
            release_id=release_id,
            latest_snapshot=latest_snapshot,
        )

    return ReleaseSignalResponse(
        release_id=signal_row.release_id,
        signal=readiness_details.get("signal", signal_row.signal),
        status_label=readiness_details.get("status_label"),
        confidence_score=readiness_details.get("confidence_score"),
        summary=readiness_details.get("summary"),
        reasons=signal_row.reasons,
        reason_details=reason_details,
        release_gates=readiness_details.get("release_gates", []),
        critical_risks=readiness_details.get("critical_risks", []),
        warnings=readiness_details.get("warnings", []),
        primary_risk=readiness_details.get("primary_risk"),
        risk_aging=risk_aging,
        last_24_hours=last_24_hours,
        thresholds=_build_thresholds(),
        updated_at=signal_row.updated_at,
    )
