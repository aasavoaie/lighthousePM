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

    RISK_WEIGHTS = {
        "open_blockers": 28.0,
        "open_high_severity_bugs_red": 18.0,
        "open_high_severity_bugs_yellow": 9.0,
        "scope_churn_7d_pct_red": 8.0,
        "scope_churn_7d_pct_yellow": 4.0,
        "reopen_rate_pct_red": 6.0,
        "reopen_rate_pct_yellow": 3.0,
        "median_cycle_time_days_yellow": 4.0,
    }

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
    def _build_release_readiness_details(
        signal: str | None,
        open_blockers: int,
        open_high_severity_bugs: int,
        scope_churn_7d_pct: float,
        reopen_rate_pct: float,
        median_cycle_time_days: float | None,
    ) -> dict[str, object]:
        """Build deterministic release-readiness details for the signal UI."""
        scope_churn_red_pct = SCOPE_CHURN_RED_THRESHOLD * 100
        scope_churn_yellow_pct = SCOPE_CHURN_YELLOW_THRESHOLD * 100
        reopen_rate_red_pct = REOPEN_RATE_RED_THRESHOLD * 100
        reopen_rate_yellow_pct = REOPEN_RATE_YELLOW_THRESHOLD * 100

        gates: list[dict[str, object]] = [
            {
                "metric_name": "open_blockers",
                "label": "No blockers",
                "passed": open_blockers <= OPEN_BLOCKERS_RED_THRESHOLD,
                "value": open_blockers,
                "comparison": "<=",
                "threshold": OPEN_BLOCKERS_RED_THRESHOLD,
            },
            {
                "metric_name": "open_high_severity_bugs",
                "label": f"High severity bugs <= {HIGH_SEVERITY_BUGS_RED_THRESHOLD}",
                "passed": open_high_severity_bugs <= HIGH_SEVERITY_BUGS_RED_THRESHOLD,
                "value": open_high_severity_bugs,
                "comparison": "<=",
                "threshold": HIGH_SEVERITY_BUGS_RED_THRESHOLD,
            },
            {
                "metric_name": "scope_churn_7d_pct",
                "label": f"Scope churn <= {scope_churn_red_pct:.0f}%",
                "passed": scope_churn_7d_pct <= scope_churn_red_pct,
                "value": scope_churn_7d_pct,
                "comparison": "<=",
                "threshold": float(scope_churn_red_pct),
            },
            {
                "metric_name": "reopen_rate_pct",
                "label": f"Reopen rate <= {reopen_rate_red_pct:.0f}%",
                "passed": reopen_rate_pct <= reopen_rate_red_pct,
                "value": reopen_rate_pct,
                "comparison": "<=",
                "threshold": float(reopen_rate_red_pct),
            },
            {
                "metric_name": "median_cycle_time_days",
                "label": f"Cycle time <= {CYCLE_TIME_YELLOW_THRESHOLD_DAYS:.0f}d",
                "passed": median_cycle_time_days is None
                or median_cycle_time_days <= CYCLE_TIME_YELLOW_THRESHOLD_DAYS,
                "value": median_cycle_time_days,
                "comparison": "<=",
                "threshold": CYCLE_TIME_YELLOW_THRESHOLD_DAYS,
            },
        ]

        risk_points: dict[str, float] = {}
        critical_risks: list[dict[str, object]] = []
        warnings: list[dict[str, object]] = []

        if open_blockers > OPEN_BLOCKERS_RED_THRESHOLD:
            points = SignalService.RISK_WEIGHTS["open_blockers"]
            risk_points["open_blockers"] = points
            critical_risks.append(
                {
                    "metric_name": "open_blockers",
                    "level": "CRITICAL",
                    "message": f"{open_blockers} blockers remain open",
                    "value": open_blockers,
                    "contribution_pct": 0.0,
                }
            )

        if open_high_severity_bugs > HIGH_SEVERITY_BUGS_RED_THRESHOLD:
            points = SignalService.RISK_WEIGHTS["open_high_severity_bugs_red"]
            risk_points["open_high_severity_bugs"] = points
            critical_risks.append(
                {
                    "metric_name": "open_high_severity_bugs",
                    "level": "CRITICAL",
                    "message": f"{open_high_severity_bugs} high severity bugs remain unresolved",
                    "value": open_high_severity_bugs,
                    "contribution_pct": 0.0,
                }
            )
        elif open_high_severity_bugs > HIGH_SEVERITY_BUGS_YELLOW_THRESHOLD:
            points = SignalService.RISK_WEIGHTS["open_high_severity_bugs_yellow"]
            risk_points["open_high_severity_bugs"] = points
            warnings.append(
                {
                    "metric_name": "open_high_severity_bugs",
                    "level": "WARNING",
                    "message": f"{open_high_severity_bugs} high severity bug remains unresolved",
                    "value": open_high_severity_bugs,
                    "contribution_pct": 0.0,
                }
            )

        if scope_churn_7d_pct > scope_churn_red_pct:
            points = SignalService.RISK_WEIGHTS["scope_churn_7d_pct_red"]
            risk_points["scope_churn_7d_pct"] = points
            warnings.append(
                {
                    "metric_name": "scope_churn_7d_pct",
                    "level": "WARNING",
                    "message": f"Scope churn increased to {scope_churn_7d_pct:.0f}%",
                    "value": scope_churn_7d_pct,
                    "contribution_pct": 0.0,
                }
            )
        elif scope_churn_7d_pct > scope_churn_yellow_pct:
            points = SignalService.RISK_WEIGHTS["scope_churn_7d_pct_yellow"]
            risk_points["scope_churn_7d_pct"] = points
            warnings.append(
                {
                    "metric_name": "scope_churn_7d_pct",
                    "level": "WARNING",
                    "message": f"Scope churn increased to {scope_churn_7d_pct:.0f}%",
                    "value": scope_churn_7d_pct,
                    "contribution_pct": 0.0,
                }
            )

        if reopen_rate_pct > reopen_rate_red_pct:
            points = SignalService.RISK_WEIGHTS["reopen_rate_pct_red"]
            risk_points["reopen_rate_pct"] = points
            warnings.append(
                {
                    "metric_name": "reopen_rate_pct",
                    "level": "WARNING",
                    "message": "Reopen rate exceeds target",
                    "value": reopen_rate_pct,
                    "contribution_pct": 0.0,
                }
            )
        elif reopen_rate_pct > reopen_rate_yellow_pct:
            points = SignalService.RISK_WEIGHTS["reopen_rate_pct_yellow"]
            risk_points["reopen_rate_pct"] = points
            warnings.append(
                {
                    "metric_name": "reopen_rate_pct",
                    "level": "WARNING",
                    "message": "Reopen rate exceeds target",
                    "value": reopen_rate_pct,
                    "contribution_pct": 0.0,
                }
            )

        if median_cycle_time_days is not None and median_cycle_time_days > CYCLE_TIME_YELLOW_THRESHOLD_DAYS:
            points = SignalService.RISK_WEIGHTS["median_cycle_time_days_yellow"]
            risk_points["median_cycle_time_days"] = points
            warnings.append(
                {
                    "metric_name": "median_cycle_time_days",
                    "level": "WARNING",
                    "message": "Median cycle time exceeds target",
                    "value": median_cycle_time_days,
                    "contribution_pct": 0.0,
                }
            )

        total_risk_points = sum(risk_points.values())
        confidence_score = round(max(0.0, 100.0 - total_risk_points), 1)
        contribution_by_metric = {
            metric_name: round((points / total_risk_points) * 100, 1)
            for metric_name, points in risk_points.items()
        } if total_risk_points > 0 else {}

        for item in critical_risks + warnings:
            item["contribution_pct"] = contribution_by_metric.get(str(item["metric_name"]), 0.0)

        primary_risk = None
        if risk_points:
            primary_metric_name = max(risk_points, key=risk_points.get)
            label_by_metric = {
                "open_blockers": "Open blockers",
                "open_high_severity_bugs": "High severity bugs",
                "scope_churn_7d_pct": "Scope churn",
                "reopen_rate_pct": "Reopen rate",
                "median_cycle_time_days": "Cycle time",
            }
            primary_risk = {
                "metric_name": primary_metric_name,
                "label": label_by_metric[primary_metric_name],
                "message": (
                    f"{label_by_metric[primary_metric_name]} contribute "
                    f"{contribution_by_metric[primary_metric_name]:.0f}% of total release risk."
                ),
                "contribution_pct": contribution_by_metric[primary_metric_name],
            }

        status_labels = {
            "RED": "NOT READY FOR RELEASE",
            "YELLOW": "RELEASE NEEDS ATTENTION",
            "GREEN": "READY FOR RELEASE",
        }
        summaries = {
            "RED": "Current release has significant delivery and quality risks.",
            "YELLOW": "Current release has warnings that should be reviewed before release.",
            "GREEN": "Current release is within configured delivery and quality gates.",
        }

        return {
            "status_label": status_labels.get(signal or "", "NOT COMPUTED"),
            "confidence_score": confidence_score,
            "summary": summaries.get(signal or "", "Signal has not been computed yet for this release snapshot."),
            "release_gates": gates,
            "critical_risks": critical_risks,
            "warnings": warnings,
            "primary_risk": primary_risk,
        }

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
