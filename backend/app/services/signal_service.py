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
        churn_ratio = scope_churn_7d_pct / 100.0
        reopen_ratio = reopen_rate_pct / 100.0

        # RED signal triggers: conditions that typically block release or pose critical risk
        red_reasons: list[str] = []

        # RED: Any open blocker indicates dependency or critical-path blocking.
        # Threshold: exactly 0 (>0 is RED). Even one blocker warrants stopping the release.
        if open_blockers > OPEN_BLOCKERS_RED_THRESHOLD:
            red_reasons.append(f"Open blockers: {open_blockers} > {OPEN_BLOCKERS_RED_THRESHOLD}")

        # RED: More than one high-severity bug indicates quality concerns.
        # Threshold: >1 bugs (2+ is RED). One bug is monitored (YELLOW), two+ stop release.
        if open_high_severity_bugs > HIGH_SEVERITY_BUGS_RED_THRESHOLD:
            red_reasons.append(
                f"High-severity bugs: {open_high_severity_bugs} > {HIGH_SEVERITY_BUGS_RED_THRESHOLD}"
            )

        # RED: Scope churn >20% in last 7 days indicates instability/late changes.
        # Threshold: >20% (20.1% is RED, 20.0% is YELLOW). Late scope changes destabilize releases.
        if churn_ratio > SCOPE_CHURN_RED_THRESHOLD:
            red_reasons.append(
                f"Scope churn: {scope_churn_7d_pct:.1f}% > {SCOPE_CHURN_RED_THRESHOLD * 100:.0f}%"
            )

        # RED: Reopen rate >15% indicates testing/quality issues.
        # Threshold: >15% (15.1% is RED, 15.0% is YELLOW). High reopen rates suggest insufficient testing.
        if reopen_ratio > REOPEN_RATE_RED_THRESHOLD:
            red_reasons.append(
                f"Reopen rate: {reopen_rate_pct:.1f}% > {REOPEN_RATE_RED_THRESHOLD * 100:.0f}%"
            )

        if red_reasons:
            return "RED", red_reasons

        # YELLOW signal triggers: conditions that warrant attention before release but don't block
        yellow_reasons: list[str] = []

        # YELLOW: Any open high-severity bug (>0) warrants attention even if not RED.
        # Threshold: >0 bugs. One bug should be reviewed before release (RED is >1).
        if open_high_severity_bugs > HIGH_SEVERITY_BUGS_YELLOW_THRESHOLD:
            yellow_reasons.append(f"High-severity bugs present: {open_high_severity_bugs} > {HIGH_SEVERITY_BUGS_YELLOW_THRESHOLD}")

        # YELLOW: Scope churn 10-20% indicates notable late changes.
        # Threshold: >10% (10.1% is YELLOW). Some late changes are expected; >10% is notable.
        if churn_ratio > SCOPE_CHURN_YELLOW_THRESHOLD:
            yellow_reasons.append(
                f"Scope churn: {scope_churn_7d_pct:.1f}% > {SCOPE_CHURN_YELLOW_THRESHOLD * 100:.0f}%"
            )

        # YELLOW: Reopen rate 10-15% indicates some quality concerns.
        # Threshold: >10% (10.1% is YELLOW). Moderate reopen rates suggest testing gaps.
        if reopen_ratio > REOPEN_RATE_YELLOW_THRESHOLD:
            yellow_reasons.append(
                f"Reopen rate: {reopen_rate_pct:.1f}% > {REOPEN_RATE_YELLOW_THRESHOLD * 100:.0f}%"
            )

        # YELLOW: Elevated cycle time (>7d median) indicates slowdown in delivery.
        # Threshold: >7 days. Moderate slowdown may indicate process bottlenecks (not critical).
        if median_cycle_time_days is not None and median_cycle_time_days > CYCLE_TIME_YELLOW_THRESHOLD_DAYS:
            yellow_reasons.append(
                f"Median cycle time: {median_cycle_time_days:.1f}d > {CYCLE_TIME_YELLOW_THRESHOLD_DAYS:.1f}d"
            )

        if yellow_reasons:
            return "YELLOW", yellow_reasons

        # GREEN: No risk indicators. Release is ready (all metrics nominal).
        return "GREEN", ["No major risk indicators"]
