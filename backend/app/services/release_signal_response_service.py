from datetime import datetime
from typing import cast

from sqlalchemy.orm import Session

from app.metric_catalog import RELEASE_THRESHOLD_METADATA
from app.models import MetricSnapshot
from app.repositories.metric_repository import MetricRepository
from app.repositories.release_repository import ReleaseRepository
from app.repositories.signal_repository import SignalRepository
from app.schemas.signals import (
    ReleaseOutlook,
    ReleaseSignalResponse,
    SignalGate,
    SignalLast24Hours,
    SignalPrimaryRisk,
    SignalReasonDetail,
    SignalRiskAging,
    SignalRiskItem,
    SignalThresholds,
)
from app.services.application_errors import ApplicationNotFoundError
from app.services.signal_service import SignalService


class ReleaseSignalResponseService:
    """Assemble release-signal API responses from stored artifacts."""

    @staticmethod
    def _empty_risk_aging() -> dict[str, object]:
        empty_group: dict[str, object] = {
            "count": 0,
            "known_count": 0,
            "unknown_count": 0,
            "oldest_age_days": None,
            "average_age_days": None,
            "tickets": [],
        }
        return {
            "blockers": empty_group,
            "high_severity_bugs": empty_group,
            "as_of": None,
        }

    @staticmethod
    def _empty_last_24_hours() -> dict[str, object]:
        return {
            "as_of": None,
            "baseline_at": None,
            "has_baseline": False,
            "unavailable_reason": None,
            "items": [],
        }

    @staticmethod
    def _build_thresholds() -> SignalThresholds:
        return SignalThresholds.model_validate(dict(RELEASE_THRESHOLD_METADATA))

    @staticmethod
    def _optional_string(value: object) -> str | None:
        return value if isinstance(value, str) else None

    @staticmethod
    def _object_dict_list(value: object) -> list[dict[str, object]]:
        return cast(list[dict[str, object]], value) if isinstance(value, list) else []

    def _not_computed_response(
        self,
        *,
        release_id: str,
        summary: str,
        reasons: list[str],
        release_date: datetime | None = None,
        latest_snapshot: MetricSnapshot | None = None,
        metric_snapshot_id: int | None = None,
        ruleset_version: int = 0,
        calculated_at: datetime | None = None,
        updated_at: datetime | None = None,
    ) -> ReleaseSignalResponse:
        last_24_hours = self._empty_last_24_hours()
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
            risk_aging=SignalRiskAging.model_validate(self._empty_risk_aging()),
            last_24_hours=SignalLast24Hours.model_validate(last_24_hours),
            release_outlook=ReleaseOutlook.model_validate(
                SignalService._build_release_outlook(
                    release_date=release_date,
                    latest_snapshot=latest_snapshot,
                    final_signal=None,
                    confidence_score=None,
                    release_gates=[],
                    critical_risks=[],
                    warnings=[],
                    last_24_hours=last_24_hours,
                )
            ),
            thresholds=self._build_thresholds() if ruleset_version > 0 else None,
            calculated_at=calculated_at,
            updated_at=updated_at,
        )

    def get_signal(
        self,
        *,
        session: Session,
        release_id: str,
    ) -> ReleaseSignalResponse:
        release = ReleaseRepository.get_release_by_id(
            session=session,
            release_id=release_id,
        )
        if release is None:
            raise ApplicationNotFoundError(f"Release '{release_id}' not found")

        signal_row = SignalRepository.get_latest_signal(
            session=session,
            release_id=release_id,
        )
        latest_snapshot = MetricRepository.get_latest_snapshot(
            session=session,
            release_id=release_id,
        )
        if (
            ReleaseRepository.count_release_issues(
                session=session,
                release_id=release_id,
            )
            == 0
        ):
            reasons = (
                signal_row.reasons
                if signal_row is not None
                else ["No tickets are assigned to this release."]
            )
            return self._not_computed_response(
                release_id=release_id,
                summary=(
                    "Release signal is not computed because no tickets are assigned "
                    "to this release."
                ),
                reasons=reasons,
                release_date=release.release_date,
                latest_snapshot=latest_snapshot,
                metric_snapshot_id=(
                    signal_row.metric_snapshot_id if signal_row is not None else None
                ),
                ruleset_version=(
                    signal_row.ruleset_version if signal_row is not None else 0
                ),
                calculated_at=(
                    signal_row.calculated_at if signal_row is not None else None
                ),
                updated_at=signal_row.updated_at if signal_row is not None else None,
            )

        if signal_row is None:
            return self._not_computed_response(
                release_id=release_id,
                summary="Signal has not been computed yet for this release snapshot.",
                reasons=[],
                release_date=release.release_date,
                latest_snapshot=latest_snapshot,
            )

        reason_details: list[SignalReasonDetail] = []
        readiness_details: dict[str, object] = {}
        risk_aging: dict[str, object] = self._empty_risk_aging()
        last_24_hours: dict[str, object] = self._empty_last_24_hours()
        confidence_breakdown = None
        biggest_driver = None
        if latest_snapshot is not None:
            if (
                signal_row.ruleset_version > 0
                and signal_row.metric_snapshot_id == latest_snapshot.id
            ):
                reason_details = [
                    SignalReasonDetail.model_validate(detail)
                    for detail in signal_row.reason_details
                ]
                readiness_details = signal_row.readiness_evidence
                risk_aging = (
                    signal_row.risk_aging_evidence or self._empty_risk_aging()
                )
            last_24_hours = SignalService._build_last_24_hours(
                session=session,
                release_id=release_id,
                latest_snapshot=latest_snapshot,
            )
            outputs = (latest_snapshot.calculation_provenance or {}).get(
                "component_outputs",
                {},
            )
            if latest_snapshot.ruleset_version > 0 and isinstance(outputs, dict):
                confidence_breakdown = outputs.get("confidence_breakdown")
                biggest_driver = outputs.get("biggest_driver")

        response_signal = self._optional_string(readiness_details.get("signal")) or (
            signal_row.signal if signal_row.signal != "NOT_COMPUTED" else None
        )
        final_signal = response_signal if signal_row.ruleset_version > 0 else None
        release_gates = (
            signal_row.release_gates if signal_row.ruleset_version > 0 else []
        )
        critical_risks = self._object_dict_list(
            readiness_details.get("critical_risks", [])
        )
        warnings = self._object_dict_list(readiness_details.get("warnings", []))
        primary_risk_value = readiness_details.get("primary_risk")
        confidence_score = (
            signal_row.confidence_score if signal_row.ruleset_version > 0 else None
        )
        return ReleaseSignalResponse(
            release_id=signal_row.release_id,
            metric_snapshot_id=signal_row.metric_snapshot_id,
            ruleset_version=signal_row.ruleset_version,
            signal=response_signal,
            status_label=(
                self._optional_string(readiness_details.get("status_label"))
                if signal_row.ruleset_version > 0
                else "Unversioned legacy result"
            ),
            confidence_score=confidence_score,
            confidence_breakdown=confidence_breakdown,
            biggest_driver=biggest_driver,
            summary=self._optional_string(readiness_details.get("summary")),
            reasons=signal_row.reasons,
            reason_details=reason_details,
            release_gates=[
                SignalGate.model_validate(gate) for gate in release_gates
            ],
            critical_risks=[
                SignalRiskItem.model_validate(item) for item in critical_risks
            ],
            warnings=[SignalRiskItem.model_validate(item) for item in warnings],
            primary_risk=(
                SignalPrimaryRisk.model_validate(primary_risk_value)
                if primary_risk_value is not None
                else None
            ),
            risk_aging=SignalRiskAging.model_validate(risk_aging),
            last_24_hours=SignalLast24Hours.model_validate(last_24_hours),
            release_outlook=ReleaseOutlook.model_validate(
                SignalService._build_release_outlook(
                    release_date=release.release_date,
                    latest_snapshot=latest_snapshot,
                    final_signal=final_signal,
                    confidence_score=confidence_score,
                    release_gates=release_gates,
                    critical_risks=critical_risks,
                    warnings=warnings,
                    last_24_hours=last_24_hours,
                )
            ),
            thresholds=(
                SignalThresholds.model_validate(
                    (latest_snapshot.calculation_provenance or {}).get(
                        "thresholds",
                        {},
                    )
                )
                if latest_snapshot is not None
                and latest_snapshot.ruleset_version > 0
                and (latest_snapshot.calculation_provenance or {}).get("thresholds")
                else None
            ),
            calculated_at=signal_row.calculated_at,
            updated_at=signal_row.updated_at,
        )
