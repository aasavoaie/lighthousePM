import logging

from sqlalchemy.orm import Session

from app.repositories.metric_repository import MetricRepository
from app.repositories.operational_status_repository import OperationalStatusRepository
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

logger = logging.getLogger(__name__)


class SignalService:
    """
    Rule-based deterministic release signal computation.

    Evaluates metric snapshots against centralized thresholds to produce RED/YELLOW/GREEN
    signals. All thresholds are explicit, testable, and documented.

    Signal Levels:
    - RED: High-risk conditions that typically block or delay release.
    - YELLOW: Moderate-risk conditions that warrant attention before release.
    - GREEN: No significant risk indicators; release readiness nominal.

    Thresholds are defined in constants.py and include:
    - RED triggers: open blockers, critical bugs, scope churn, quality concerns
    - YELLOW triggers: moderate bugs, scope churn, cycle time, reopen rates
    - GREEN: default when no risk indicators present

    Each signal includes explicit reasons (list of strings) explaining what triggered it.
    """

    def recompute_release_signal(self, session: Session, release_id: str):
        logger.info("signal_recompute_started release_id=%s", release_id)
        release = ReleaseRepository.get_release_by_id(session=session, release_id=release_id)
        if release is None:
            raise ValueError(f"Release not found: {release_id!r}")

        # Analytics recompute may have just added a new MetricSnapshot in this
        # transaction; flush so subsequent SELECT sees pending rows.
        session.flush()
        snapshot = MetricRepository.get_latest_snapshot(session=session, release_id=release_id)
        if snapshot is None:
            raise ValueError(f"No metric snapshot found for release: {release_id!r}")

        signal, reasons, _ = self._evaluate_signal_with_details(
            open_blockers=snapshot.open_blockers,
            open_high_severity_bugs=snapshot.open_high_severity_bugs,
            scope_churn_7d_pct=snapshot.scope_churn_7d_pct,
            reopen_rate_pct=snapshot.reopen_rate_pct,
            median_cycle_time_days=snapshot.median_cycle_time_days,
        )

        OperationalStatusRepository.mark_signal_recomputed(session=session)
        logger.info(
            "signal_recompute_completed release_id=%s signal=%s reason_count=%d",
            release_id,
            signal,
            len(reasons),
        )

        return SignalRepository.upsert_signal(
            session=session,
            release_id=release_id,
            signal=signal,
            reasons=reasons,
        )

    @staticmethod
    def _evaluate_signal_with_details(
        open_blockers: int,
        open_high_severity_bugs: int,
        scope_churn_7d_pct: float,
        reopen_rate_pct: float,
        median_cycle_time_days: float | None,
    ) -> tuple[str, list[str], list[dict[str, str | int | float]]]:
        """Apply deterministic rules and return signal, reasons, and structured reason details."""
        churn_ratio = scope_churn_7d_pct / 100.0
        reopen_ratio = reopen_rate_pct / 100.0

        red_reasons: list[str] = []
        red_details: list[dict[str, str | int | float]] = []

        if open_blockers > OPEN_BLOCKERS_RED_THRESHOLD:
            message = f"Open blockers: {open_blockers} > {OPEN_BLOCKERS_RED_THRESHOLD}"
            red_reasons.append(message)
            red_details.append(
                {
                    "metric_name": "open_blockers",
                    "level": "RED",
                    "value": open_blockers,
                    "comparison": ">",
                    "threshold": OPEN_BLOCKERS_RED_THRESHOLD,
                    "message": message,
                }
            )

        if open_high_severity_bugs > HIGH_SEVERITY_BUGS_RED_THRESHOLD:
            message = (
                f"High-severity bugs: {open_high_severity_bugs} > {HIGH_SEVERITY_BUGS_RED_THRESHOLD}"
            )
            red_reasons.append(message)
            red_details.append(
                {
                    "metric_name": "open_high_severity_bugs",
                    "level": "RED",
                    "value": open_high_severity_bugs,
                    "comparison": ">",
                    "threshold": HIGH_SEVERITY_BUGS_RED_THRESHOLD,
                    "message": message,
                }
            )

        if churn_ratio > SCOPE_CHURN_RED_THRESHOLD:
            threshold_pct = SCOPE_CHURN_RED_THRESHOLD * 100
            message = f"Scope churn: {scope_churn_7d_pct:.1f}% > {threshold_pct:.0f}%"
            red_reasons.append(message)
            red_details.append(
                {
                    "metric_name": "scope_churn_7d_pct",
                    "level": "RED",
                    "value": scope_churn_7d_pct,
                    "comparison": ">",
                    "threshold": float(threshold_pct),
                    "message": message,
                }
            )

        if reopen_ratio > REOPEN_RATE_RED_THRESHOLD:
            threshold_pct = REOPEN_RATE_RED_THRESHOLD * 100
            message = f"Reopen rate: {reopen_rate_pct:.1f}% > {threshold_pct:.0f}%"
            red_reasons.append(message)
            red_details.append(
                {
                    "metric_name": "reopen_rate_pct",
                    "level": "RED",
                    "value": reopen_rate_pct,
                    "comparison": ">",
                    "threshold": float(threshold_pct),
                    "message": message,
                }
            )

        if red_reasons:
            return "RED", red_reasons, red_details

        yellow_reasons: list[str] = []
        yellow_details: list[dict[str, str | int | float]] = []

        if open_high_severity_bugs > HIGH_SEVERITY_BUGS_YELLOW_THRESHOLD:
            message = (
                f"High-severity bugs present: {open_high_severity_bugs} > {HIGH_SEVERITY_BUGS_YELLOW_THRESHOLD}"
            )
            yellow_reasons.append(message)
            yellow_details.append(
                {
                    "metric_name": "open_high_severity_bugs",
                    "level": "YELLOW",
                    "value": open_high_severity_bugs,
                    "comparison": ">",
                    "threshold": HIGH_SEVERITY_BUGS_YELLOW_THRESHOLD,
                    "message": message,
                }
            )

        if churn_ratio > SCOPE_CHURN_YELLOW_THRESHOLD:
            threshold_pct = SCOPE_CHURN_YELLOW_THRESHOLD * 100
            message = f"Scope churn: {scope_churn_7d_pct:.1f}% > {threshold_pct:.0f}%"
            yellow_reasons.append(message)
            yellow_details.append(
                {
                    "metric_name": "scope_churn_7d_pct",
                    "level": "YELLOW",
                    "value": scope_churn_7d_pct,
                    "comparison": ">",
                    "threshold": float(threshold_pct),
                    "message": message,
                }
            )

        if reopen_ratio > REOPEN_RATE_YELLOW_THRESHOLD:
            threshold_pct = REOPEN_RATE_YELLOW_THRESHOLD * 100
            message = f"Reopen rate: {reopen_rate_pct:.1f}% > {threshold_pct:.0f}%"
            yellow_reasons.append(message)
            yellow_details.append(
                {
                    "metric_name": "reopen_rate_pct",
                    "level": "YELLOW",
                    "value": reopen_rate_pct,
                    "comparison": ">",
                    "threshold": float(threshold_pct),
                    "message": message,
                }
            )

        if median_cycle_time_days is not None and median_cycle_time_days > CYCLE_TIME_YELLOW_THRESHOLD_DAYS:
            message = (
                f"Median cycle time: {median_cycle_time_days:.1f}d > {CYCLE_TIME_YELLOW_THRESHOLD_DAYS:.1f}d"
            )
            yellow_reasons.append(message)
            yellow_details.append(
                {
                    "metric_name": "median_cycle_time_days",
                    "level": "YELLOW",
                    "value": median_cycle_time_days,
                    "comparison": ">",
                    "threshold": CYCLE_TIME_YELLOW_THRESHOLD_DAYS,
                    "message": message,
                }
            )

        if yellow_reasons:
            return "YELLOW", yellow_reasons, yellow_details

        return "GREEN", ["No major risk indicators"], []

    @staticmethod
    def _evaluate_signal(
        open_blockers: int,
        open_high_severity_bugs: int,
        scope_churn_7d_pct: float,
        reopen_rate_pct: float,
        median_cycle_time_days: float | None,
    ) -> tuple[str, list[str]]:
        """
        Apply deterministic RED/YELLOW/GREEN rules and return reasons.

        Rules are evaluated in priority order (RED before YELLOW). If any RED condition
        is triggered, signal is RED and all RED reasons are returned. If no RED conditions
        but YELLOW conditions exist, signal is YELLOW. Otherwise, signal is GREEN.

        Reason messages follow format: "{metric_name}: {value} {comparison} {threshold}".
        This makes thresholds explicit and reproducible.

        Args:
            open_blockers: Count of issues marked as blockers (typically blocking release).
            open_high_severity_bugs: Count of open bugs with high/critical priority.
            scope_churn_7d_pct: Percentage (0-100) of issues changed in last 7 days.
            reopen_rate_pct: Percentage (0-100) of issues reopened in release window.
            median_cycle_time_days: Median days from in-progress to done (None if no done issues).

        Returns:
            Tuple of (signal_string, reasons_list) where signal is "RED", "YELLOW", or "GREEN"
            and reasons is a list of strings explaining why that signal was triggered.
        """
        signal, reasons, _ = SignalService._evaluate_signal_with_details(
            open_blockers=open_blockers,
            open_high_severity_bugs=open_high_severity_bugs,
            scope_churn_7d_pct=scope_churn_7d_pct,
            reopen_rate_pct=reopen_rate_pct,
            median_cycle_time_days=median_cycle_time_days,
        )
        return signal, reasons
