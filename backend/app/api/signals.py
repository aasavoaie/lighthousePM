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
    empty_group = {
        "count": 0,
        "known_count": 0,
        "unknown_count": 0,
        "oldest_age_days": None,
        "average_age_days": None,
        "tickets": [],
    }
    return {"blockers": empty_group, "high_severity_bugs": empty_group, "as_of": None}


def _empty_last_24_hours() -> dict[str, object]:
    return {"as_of": None, "baseline_at": None, "has_baseline": False, "unavailable_reason": None, "items": []}


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


def _not_computed_signal_response(
    release_id: str,
    summary: str,
    reasons: list[str],
    release_date=None,
    latest_snapshot=None,
    metric_snapshot_id=None,
    ruleset_version=0,
    calculated_at=None,
    updated_at=None,
) -> ReleaseSignalResponse:
    last_24_hours = _empty_last_24_hours()
    return ReleaseSignalResponse(
        release_id=release_id,
        metric_snapshot_id=metric_snapshot_id,
        ruleset_version=ruleset_version,
        signal=None,
        status_label="NOT COMPUTED",
        confidence_score=None,
        confidence_breakdown=None,
        biggest_driver=None,
        summary=summary,
        reasons=reasons,
        reason_details=[],
        release_gates=[],
        critical_risks=[],
        warnings=[],
        primary_risk=None,
        risk_aging=_empty_risk_aging(),
        last_24_hours=last_24_hours,
        release_outlook=SignalService._build_release_outlook(
            release_date=release_date,
            latest_snapshot=latest_snapshot,
            final_signal=None,
            confidence_score=None,
            release_gates=[],
            critical_risks=[],
            warnings=[],
            last_24_hours=last_24_hours,
        ),
        thresholds=_build_thresholds() if ruleset_version > 0 else None,
        calculated_at=calculated_at,
        updated_at=updated_at,
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
    latest_snapshot = MetricRepository.get_latest_snapshot(session=session, release_id=release_id)
    if ReleaseRepository.count_release_issues(session=session, release_id=release_id) == 0:
        reasons = signal_row.reasons if signal_row is not None else ["No tickets are assigned to this release."]
        return _not_computed_signal_response(
            release_id=release_id,
            summary="Release signal is not computed because no tickets are assigned to this release.",
            reasons=reasons,
            release_date=release.release_date,
            latest_snapshot=latest_snapshot,
            metric_snapshot_id=signal_row.metric_snapshot_id if signal_row is not None else None,
            ruleset_version=signal_row.ruleset_version if signal_row is not None else 0,
            calculated_at=signal_row.calculated_at if signal_row is not None else None,
            updated_at=signal_row.updated_at if signal_row is not None else None,
        )

    if signal_row is None:
        return _not_computed_signal_response(
            release_id=release_id,
            summary="Signal has not been computed yet for this release snapshot.",
            reasons=[],
            release_date=release.release_date,
            latest_snapshot=latest_snapshot,
            ruleset_version=0,
        )

    reason_details: list[SignalReasonDetail] = []
    readiness_details: dict[str, object] = {}
    risk_aging: dict[str, object] = _empty_risk_aging()
    last_24_hours: dict[str, object] = _empty_last_24_hours()
    confidence_breakdown = None
    biggest_driver = None
    if latest_snapshot is not None:
        if signal_row.ruleset_version > 0 and signal_row.metric_snapshot_id == latest_snapshot.id:
            reason_details = [
                SignalReasonDetail.model_validate(detail) for detail in signal_row.reason_details
            ]
            readiness_details = signal_row.readiness_evidence
            risk_aging = signal_row.risk_aging_evidence or _empty_risk_aging()
        last_24_hours = SignalService._build_last_24_hours(
            session=session,
            release_id=release_id,
            latest_snapshot=latest_snapshot,
        )
        outputs = (latest_snapshot.calculation_provenance or {}).get("component_outputs", {})
        if latest_snapshot.ruleset_version > 0 and isinstance(outputs, dict):
            confidence_breakdown = outputs.get("confidence_breakdown")
            biggest_driver = outputs.get("biggest_driver")

    response_signal = readiness_details.get("signal") or (signal_row.signal if signal_row.signal != "NOT_COMPUTED" else None)
    final_signal = response_signal if signal_row.ruleset_version > 0 else None
    release_gates = signal_row.release_gates if signal_row.ruleset_version > 0 else []
    critical_risks = readiness_details.get("critical_risks", [])
    warnings = readiness_details.get("warnings", [])
    confidence_score = signal_row.confidence_score if signal_row.ruleset_version > 0 else None
    return ReleaseSignalResponse(
        release_id=signal_row.release_id,
        metric_snapshot_id=signal_row.metric_snapshot_id,
        ruleset_version=signal_row.ruleset_version,
        signal=response_signal,
        status_label=(
            readiness_details.get("status_label")
            if signal_row.ruleset_version > 0
            else "Unversioned legacy result"
        ),
        confidence_score=confidence_score,
        confidence_breakdown=confidence_breakdown,
        biggest_driver=biggest_driver,
        summary=readiness_details.get("summary"),
        reasons=signal_row.reasons,
        reason_details=reason_details,
        release_gates=release_gates,
        critical_risks=critical_risks,
        warnings=warnings,
        primary_risk=readiness_details.get("primary_risk"),
        risk_aging=risk_aging,
        last_24_hours=last_24_hours,
        release_outlook=SignalService._build_release_outlook(
            release_date=release.release_date,
            latest_snapshot=latest_snapshot,
            final_signal=final_signal,
            confidence_score=confidence_score,
            release_gates=release_gates,
            critical_risks=critical_risks,
            warnings=warnings,
            last_24_hours=last_24_hours,
        ),
        thresholds=(
            SignalThresholds.model_validate(
                (latest_snapshot.calculation_provenance or {}).get("thresholds", {})
            )
            if latest_snapshot is not None
            and latest_snapshot.ruleset_version > 0
            and (latest_snapshot.calculation_provenance or {}).get("thresholds")
            else None
        ),
        calculated_at=signal_row.calculated_at,
        updated_at=signal_row.updated_at,
    )
