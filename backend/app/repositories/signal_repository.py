from datetime import datetime

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.models import ReleaseSignal


class SignalRepository:
    """Read/write queries for release signals.

    Signal results are append-only and uniquely linked to a metric snapshot and
    ruleset version.
    """

    @staticmethod
    def get_latest_signal(session: Session, release_id: str) -> ReleaseSignal | None:
        query = (
            select(ReleaseSignal)
            .where(ReleaseSignal.release_id == release_id)
            .order_by(desc(ReleaseSignal.calculated_at), desc(ReleaseSignal.id))
            .limit(1)
        )
        return session.scalar(query)

    @staticmethod
    def get_signal_for_snapshot(
        session: Session,
        release_id: str,
        metric_snapshot_id: int,
        ruleset_version: int,
    ) -> ReleaseSignal | None:
        return session.scalar(
            select(ReleaseSignal).where(
                ReleaseSignal.release_id == release_id,
                ReleaseSignal.metric_snapshot_id == metric_snapshot_id,
                ReleaseSignal.ruleset_version == ruleset_version,
            )
        )

    @staticmethod
    def create_signal(
        session: Session,
        release_id: str,
        metric_snapshot_id: int | None,
        ruleset_version: int,
        signal: str,
        confidence_score: float | None,
        reasons: list[str],
        reason_details: list[dict[str, object]],
        release_gates: list[dict[str, object]],
        readiness_evidence: dict[str, object],
        risk_aging_evidence: dict[str, object],
        calculated_at: datetime,
    ) -> ReleaseSignal:
        existing = session.scalar(
            select(ReleaseSignal).where(
                ReleaseSignal.release_id == release_id,
                ReleaseSignal.metric_snapshot_id == metric_snapshot_id,
                ReleaseSignal.ruleset_version == ruleset_version,
            )
        )
        if existing is not None:
            return existing

        result = ReleaseSignal(
            release_id=release_id,
            metric_snapshot_id=metric_snapshot_id,
            ruleset_version=ruleset_version,
            signal=signal,
            confidence_score=confidence_score,
            reasons=reasons,
            reason_details=reason_details,
            release_gates=release_gates,
            readiness_evidence=readiness_evidence,
            risk_aging_evidence=risk_aging_evidence,
            calculated_at=calculated_at,
        )
        session.add(result)
        return result
