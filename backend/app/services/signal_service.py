from sqlalchemy.orm import Session

from app.repositories.metric_repository import MetricRepository
from app.repositories.release_repository import ReleaseRepository
from app.repositories.signal_repository import SignalRepository
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


class SignalService:
    """Rule-based deterministic release signal computation."""

    def recompute_release_signal(self, session: Session, release_id: str):
        release = ReleaseRepository.get_release_by_id(session=session, release_id=release_id)
        if release is None:
            raise ValueError(f"Release not found: {release_id!r}")

        # Analytics recompute may have just added a new MetricSnapshot in this
        # transaction; flush so subsequent SELECT sees pending rows.
        session.flush()
        snapshot = MetricRepository.get_latest_snapshot(session=session, release_id=release_id)
        if snapshot is None:
            raise ValueError(f"No metric snapshot found for release: {release_id!r}")

        signal, reasons = self._evaluate_signal(
            open_blockers=snapshot.open_blockers,
            open_high_severity_bugs=snapshot.open_high_severity_bugs,
            scope_churn_7d_pct=snapshot.scope_churn_7d_pct,
            reopen_rate_pct=snapshot.reopen_rate_pct,
            median_cycle_time_days=snapshot.median_cycle_time_days,
        )

        return SignalRepository.upsert_signal(
            session=session,
            release_id=release_id,
            signal=signal,
            reasons=reasons,
        )

    @staticmethod
    def _evaluate_signal(
        open_blockers: int,
        open_high_severity_bugs: int,
        scope_churn_7d_pct: float,
        reopen_rate_pct: float,
        median_cycle_time_days: float | None,
    ) -> tuple[str, list[str]]:
        """Apply deterministic RED/YELLOW/GREEN rules and return reasons."""
        churn_ratio = scope_churn_7d_pct / 100.0
        reopen_ratio = reopen_rate_pct / 100.0

        red_reasons: list[str] = []
        if open_blockers > OPEN_BLOCKERS_RED_THRESHOLD:
            red_reasons.append(f"{open_blockers} open blockers")
        if open_high_severity_bugs > HIGH_SEVERITY_BUGS_RED_THRESHOLD:
            red_reasons.append(
                f"Open high-severity bugs above threshold ({open_high_severity_bugs} > {HIGH_SEVERITY_BUGS_RED_THRESHOLD})"
            )
        if churn_ratio > SCOPE_CHURN_RED_THRESHOLD:
            red_reasons.append(
                f"Scope churn above red threshold ({scope_churn_7d_pct:.2f}% > {SCOPE_CHURN_RED_THRESHOLD * 100:.0f}%)"
            )
        if reopen_ratio > REOPEN_RATE_RED_THRESHOLD:
            red_reasons.append(
                f"Reopen rate above red threshold ({reopen_rate_pct:.2f}% > {REOPEN_RATE_RED_THRESHOLD * 100:.0f}%)"
            )
        if red_reasons:
            return "RED", red_reasons

        yellow_reasons: list[str] = []
        if open_high_severity_bugs > HIGH_SEVERITY_BUGS_YELLOW_THRESHOLD:
            yellow_reasons.append(
                f"Open high-severity bugs present ({open_high_severity_bugs})"
            )
        if churn_ratio > SCOPE_CHURN_YELLOW_THRESHOLD:
            yellow_reasons.append(
                f"Scope churn above yellow threshold ({scope_churn_7d_pct:.2f}% > {SCOPE_CHURN_YELLOW_THRESHOLD * 100:.0f}%)"
            )
        if reopen_ratio > REOPEN_RATE_YELLOW_THRESHOLD:
            yellow_reasons.append(
                f"Reopen rate above yellow threshold ({reopen_rate_pct:.2f}% > {REOPEN_RATE_YELLOW_THRESHOLD * 100:.0f}%)"
            )
        if median_cycle_time_days is not None and median_cycle_time_days > CYCLE_TIME_YELLOW_THRESHOLD_DAYS:
            yellow_reasons.append(
                f"Median cycle time elevated ({median_cycle_time_days:.2f}d > {CYCLE_TIME_YELLOW_THRESHOLD_DAYS:.1f}d)"
            )
        if yellow_reasons:
            return "YELLOW", yellow_reasons

        return "GREEN", ["No major risk indicators"]
