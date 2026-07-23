import logging
from datetime import UTC, datetime, timedelta
from typing import TypedDict, cast

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.metric_catalog import metric_threshold_value
from app.models import Issue, IssueHistory, MetricSnapshot
from app.repositories.metric_repository import MetricRepository
from app.repositories.operational_status_repository import OperationalStatusRepository
from app.repositories.release_repository import ReleaseRepository
from app.repositories.signal_repository import SignalRepository
from app.services.jira_field_mapper import JiraFieldMapper
from app.utils.constants import RULESET_VERSION

logger = logging.getLogger(__name__)
RELEASE_OUTLOOK_DISCLAIMER = "This outlook reflects the latest stored snapshot and is not a forecast."

OPEN_BLOCKERS_RED_THRESHOLD = metric_threshold_value(
    "release.open_blockers", "critical"
)
HIGH_SEVERITY_BUGS_RED_THRESHOLD = metric_threshold_value(
    "release.open_high_severity_bugs", "critical"
)
HIGH_SEVERITY_BUGS_YELLOW_THRESHOLD = metric_threshold_value(
    "release.open_high_severity_bugs", "watch"
)
SCOPE_CHURN_RED_THRESHOLD = (
    metric_threshold_value("release.scope_churn_7d_pct", "critical") / 100.0
)
SCOPE_CHURN_YELLOW_THRESHOLD = (
    metric_threshold_value("release.scope_churn_7d_pct", "watch") / 100.0
)
REOPEN_RATE_RED_THRESHOLD = (
    metric_threshold_value("release.reopen_rate_pct", "critical") / 100.0
)
REOPEN_RATE_YELLOW_THRESHOLD = (
    metric_threshold_value("release.reopen_rate_pct", "watch") / 100.0
)
CYCLE_TIME_YELLOW_THRESHOLD_DAYS = metric_threshold_value(
    "release.median_cycle_time_days", "watch"
)
CONFIDENCE_SCORE_RED_MAX = metric_threshold_value(
    "release.confidence_score", "critical"
)
CONFIDENCE_SCORE_YELLOW_MAX = metric_threshold_value(
    "release.confidence_score", "watch"
)


def _coerce_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


class _RiskStartEvidence(TypedDict):
    risk_started_at: datetime | None
    source_field: str | None
    source_changed_at: datetime | None


class SignalService:
    """
    Hybrid deterministic release signal computation.

    Evaluates metric snapshots against centralized hard-rule thresholds and risk
    weights. The final signal is the more severe result from the hard rules and
    the confidence-score band. All thresholds are explicit, testable, and
    documented in PRODUCT_RULES.md.

    Signal Levels:
    - RED: confidence score 0-60.
    - YELLOW: confidence score 61-90.
    - GREEN: confidence score 91-100.

    Thresholds are selected from the metric catalog and include:
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
    SEVERITY_RANK = {"GREEN": 0, "YELLOW": 1, "RED": 2}

    @staticmethod
    def _compute_release_risk_points(
        open_blockers: int,
        open_high_severity_bugs: int,
        scope_churn_7d_pct: float | None,
        reopen_rate_pct: float | None,
        median_cycle_time_days: float | None,
    ) -> dict[str, float]:
        scope_churn_red_pct = SCOPE_CHURN_RED_THRESHOLD * 100
        scope_churn_yellow_pct = SCOPE_CHURN_YELLOW_THRESHOLD * 100
        reopen_rate_red_pct = REOPEN_RATE_RED_THRESHOLD * 100
        reopen_rate_yellow_pct = REOPEN_RATE_YELLOW_THRESHOLD * 100

        risk_points: dict[str, float] = {}

        if open_blockers > OPEN_BLOCKERS_RED_THRESHOLD:
            risk_points["open_blockers"] = SignalService.RISK_WEIGHTS["open_blockers"]

        if open_high_severity_bugs > HIGH_SEVERITY_BUGS_RED_THRESHOLD:
            risk_points["open_high_severity_bugs"] = SignalService.RISK_WEIGHTS[
                "open_high_severity_bugs_red"
            ]
        elif open_high_severity_bugs > HIGH_SEVERITY_BUGS_YELLOW_THRESHOLD:
            risk_points["open_high_severity_bugs"] = SignalService.RISK_WEIGHTS[
                "open_high_severity_bugs_yellow"
            ]

        if scope_churn_7d_pct is not None and scope_churn_7d_pct > scope_churn_red_pct:
            risk_points["scope_churn_7d_pct"] = SignalService.RISK_WEIGHTS["scope_churn_7d_pct_red"]
        elif scope_churn_7d_pct is not None and scope_churn_7d_pct > scope_churn_yellow_pct:
            risk_points["scope_churn_7d_pct"] = SignalService.RISK_WEIGHTS["scope_churn_7d_pct_yellow"]

        if reopen_rate_pct is not None and reopen_rate_pct > reopen_rate_red_pct:
            risk_points["reopen_rate_pct"] = SignalService.RISK_WEIGHTS["reopen_rate_pct_red"]
        elif reopen_rate_pct is not None and reopen_rate_pct > reopen_rate_yellow_pct:
            risk_points["reopen_rate_pct"] = SignalService.RISK_WEIGHTS["reopen_rate_pct_yellow"]

        if median_cycle_time_days is not None and median_cycle_time_days > CYCLE_TIME_YELLOW_THRESHOLD_DAYS:
            risk_points["median_cycle_time_days"] = SignalService.RISK_WEIGHTS["median_cycle_time_days_yellow"]

        return risk_points

    @staticmethod
    def _compute_release_confidence_score(
        open_blockers: int,
        open_high_severity_bugs: int,
        scope_churn_7d_pct: float,
        reopen_rate_pct: float,
        median_cycle_time_days: float | None,
    ) -> float:
        risk_points = SignalService._compute_release_risk_points(
            open_blockers=open_blockers,
            open_high_severity_bugs=open_high_severity_bugs,
            scope_churn_7d_pct=scope_churn_7d_pct,
            reopen_rate_pct=reopen_rate_pct,
            median_cycle_time_days=median_cycle_time_days,
        )
        return round(max(0.0, 100.0 - sum(risk_points.values())), 1)

    @staticmethod
    def _signal_from_confidence_score(confidence_score: float) -> str:
        if confidence_score <= CONFIDENCE_SCORE_RED_MAX:
            return "RED"
        if confidence_score <= CONFIDENCE_SCORE_YELLOW_MAX:
            return "YELLOW"
        return "GREEN"

    @staticmethod
    def _most_severe_signal(*signals: str) -> str:
        """Return the most severe signal using the documented stable ordering."""
        return max(signals, key=SignalService.SEVERITY_RANK.__getitem__)

    def recompute_release_signal(self, session: Session, release_id: str):
        logger.info("signal_recompute_started release_id=%s", release_id)
        release = ReleaseRepository.get_release_by_id(session=session, release_id=release_id)
        if release is None:
            raise ValueError(f"Release not found: {release_id!r}")
        session.flush()
        snapshot = MetricRepository.get_latest_snapshot(session=session, release_id=release_id)
        calculated_at = datetime.now(UTC)
        if ReleaseRepository.count_release_issues(session=session, release_id=release_id) == 0:
            reasons = ["No tickets are assigned to this release."]
            OperationalStatusRepository.mark_signal_recomputed(session=session)
            logger.info(
                "signal_recompute_not_computed release_id=%s reason=%s",
                release_id,
                reasons[0],
            )
            return SignalRepository.create_signal(
                session=session,
                release_id=release_id,
                metric_snapshot_id=snapshot.id if snapshot is not None else None,
                ruleset_version=RULESET_VERSION,
                signal="NOT_COMPUTED",
                confidence_score=None,
                reasons=reasons,
                reason_details=[],
                release_gates=[],
                readiness_evidence={
                    "signal": None,
                    "status_label": "NOT COMPUTED",
                    "confidence_score": None,
                    "summary": "Release signal is not computed because no tickets are assigned to this release.",
                    "critical_risks": [],
                    "warnings": [],
                    "primary_risk": None,
                },
                risk_aging_evidence={
                    "blockers": {"count": 0, "known_count": 0, "unknown_count": 0, "oldest_age_days": None, "average_age_days": None, "tickets": []},
                    "high_severity_bugs": {"count": 0, "known_count": 0, "unknown_count": 0, "oldest_age_days": None, "average_age_days": None, "tickets": []},
                    "as_of": snapshot.snapshot_at.isoformat() if snapshot is not None else None,
                },
                calculated_at=calculated_at,
            )

        if snapshot is None:
            raise ValueError(f"No metric snapshot found for release: {release_id!r}")

        signal, reasons, reason_details = self._evaluate_signal_with_details(
            open_blockers=snapshot.open_blockers,
            open_high_severity_bugs=snapshot.open_high_severity_bugs,
            scope_churn_7d_pct=snapshot.scope_churn_7d_pct,
            reopen_rate_pct=snapshot.reopen_rate_pct,
            median_cycle_time_days=snapshot.median_cycle_time_days,
        )
        stored_availability = (snapshot.calculation_provenance or {}).get("availability", {})
        availability_metrics = (
            stored_availability.get("metrics", {})
            if isinstance(stored_availability, dict)
            else {}
        )
        unavailable_confidence_items = {
            metric_name: item
            for metric_name in (
                "open_blockers",
                "open_high_severity_bugs",
                "scope_churn_7d_pct",
                "reopen_rate_pct",
                "median_cycle_time_days",
            )
            if isinstance((item := availability_metrics.get(metric_name)), dict)
            and (
                item.get("status") == "PARTIAL"
                or (
                    metric_name in {"reopen_rate_pct", "median_cycle_time_days"}
                    and item.get("status") == "NOT_COMPUTED"
                )
            )
        }
        if unavailable_confidence_items:
            confirmed_hard_red = any(detail.get("level") == "RED" for detail in reason_details)
            signal = "RED" if confirmed_hard_red else "INCONCLUSIVE"
            if reasons == ["No major risk indicators"]:
                reasons = []
            for metric_name, item in unavailable_confidence_items.items():
                explanations = item.get("explanations", [])
                explanation = (
                    explanations[0]
                    if isinstance(explanations, list) and explanations
                    else item.get("reason") or "The required metric input is unavailable."
                )
                missing_keys = item.get("missing_issue_keys", [])
                missing_suffix = (
                    f" Missing Jira issue keys: {', '.join(missing_keys)}."
                    if isinstance(missing_keys, list) and missing_keys
                    else ""
                )
                reasons.append(f"{metric_name}: {explanation}{missing_suffix}")
        readiness = self._build_release_readiness_details(
            signal=signal,
            open_blockers=snapshot.open_blockers,
            open_high_severity_bugs=snapshot.open_high_severity_bugs,
            scope_churn_7d_pct=snapshot.scope_churn_7d_pct,
            reopen_rate_pct=snapshot.reopen_rate_pct,
            median_cycle_time_days=snapshot.median_cycle_time_days,
        )
        if unavailable_confidence_items:
            readiness["signal"] = signal
            readiness["status_label"] = (
                "NOT READY FOR RELEASE" if signal == "RED" else "INCONCLUSIVE"
            )
            readiness["confidence_score"] = None
            readiness["summary"] = (
                "A confirmed hard RED condition is active, and required metric inputs are unavailable or incomplete."
                if signal == "RED"
                else "Release status is inconclusive because required metric inputs are unavailable or incomplete."
            )
            unavailable_gate_metrics = set(unavailable_confidence_items)
            cycle_time_availability = unavailable_confidence_items.get(
                "median_cycle_time_days"
            )
            if (
                isinstance(cycle_time_availability, dict)
                and cycle_time_availability.get("status") == "NOT_COMPUTED"
            ):
                unavailable_gate_metrics.discard("median_cycle_time_days")
            release_gates = cast(
                list[dict[str, object]],
                readiness.get("release_gates", []),
            )
            readiness["release_gates"] = [
                gate
                for gate in release_gates
                if gate.get("metric_name") not in unavailable_gate_metrics
            ]
            readiness["unavailable_inputs"] = [
                {
                    "metric_name": metric_name,
                    "status": item.get("status"),
                    "reason": item.get("reason"),
                    "explanations": item.get("explanations", []),
                    "missing_issue_keys": item.get("missing_issue_keys", []),
                }
                for metric_name, item in unavailable_confidence_items.items()
            ]
            readiness["primary_risk"] = None
            critical_risks = cast(
                list[dict[str, object]],
                readiness.get("critical_risks", []),
            )
            warnings = cast(
                list[dict[str, object]],
                readiness.get("warnings", []),
            )
            for risk in [*critical_risks, *warnings]:
                risk["contribution_pct"] = 0.0
            readiness["reasons"] = reasons
        risk_aging = self._build_release_risk_aging(
            session=session,
            release_id=release_id,
            as_of=snapshot.snapshot_at,
            open_blocker_issue_keys=(
                snapshot.open_blocker_issue_keys
                if snapshot.open_blocker_issue_keys or snapshot.open_blockers == 0
                else None
            ),
            open_high_severity_bug_issue_keys=(
                snapshot.open_high_severity_bug_issue_keys
                if snapshot.open_high_severity_bug_issue_keys or snapshot.open_high_severity_bugs == 0
                else None
            ),
        )

        OperationalStatusRepository.mark_signal_recomputed(session=session)
        logger.info(
            "signal_recompute_completed release_id=%s signal=%s reason_count=%d",
            release_id,
            signal,
            len(reasons),
        )

        return SignalRepository.create_signal(
            session=session,
            release_id=release_id,
            metric_snapshot_id=snapshot.id,
            ruleset_version=RULESET_VERSION,
            signal=signal,
            confidence_score=snapshot.confidence_score,
            reasons=reasons,
            reason_details=[dict(detail) for detail in reason_details],
            release_gates=cast(
                list[dict[str, object]],
                readiness.get("release_gates", []),
            ),
            readiness_evidence=self._json_safe_evidence(readiness),
            risk_aging_evidence=self._json_safe_evidence(risk_aging),
            calculated_at=calculated_at,
        )

    @staticmethod
    def _json_safe_evidence(value):
        if isinstance(value, datetime):
            return _coerce_utc(value).isoformat()
        if isinstance(value, dict):
            return {key: SignalService._json_safe_evidence(item) for key, item in value.items()}
        if isinstance(value, list):
            return [SignalService._json_safe_evidence(item) for item in value]
        return value

    @staticmethod
    def _evaluate_signal_with_details(
        open_blockers: int,
        open_high_severity_bugs: int,
        scope_churn_7d_pct: float | None,
        reopen_rate_pct: float | None,
        median_cycle_time_days: float | None,
    ) -> tuple[str, list[str], list[dict[str, str | int | float]]]:
        """Apply deterministic rules and return signal, reasons, and structured reason details."""
        churn_ratio = scope_churn_7d_pct / 100.0 if scope_churn_7d_pct is not None else None
        reopen_ratio = reopen_rate_pct / 100.0 if reopen_rate_pct is not None else None

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

        if (
            churn_ratio is not None
            and scope_churn_7d_pct is not None
            and churn_ratio > SCOPE_CHURN_RED_THRESHOLD
        ):
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

        if (
            reopen_ratio is not None
            and reopen_rate_pct is not None
            and reopen_ratio > REOPEN_RATE_RED_THRESHOLD
        ):
            threshold_pct = REOPEN_RATE_RED_THRESHOLD * 100
            message = f"Reopen events per 100 eligible tickets: {reopen_rate_pct:.1f}% > {threshold_pct:.0f}%"
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

        yellow_reasons: list[str] = []
        yellow_details: list[dict[str, str | int | float]] = []

        if (
            HIGH_SEVERITY_BUGS_YELLOW_THRESHOLD
            < open_high_severity_bugs
            <= HIGH_SEVERITY_BUGS_RED_THRESHOLD
        ):
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

        if (
            churn_ratio is not None
            and scope_churn_7d_pct is not None
            and SCOPE_CHURN_YELLOW_THRESHOLD < churn_ratio <= SCOPE_CHURN_RED_THRESHOLD
        ):
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

        if (
            reopen_ratio is not None
            and reopen_rate_pct is not None
            and REOPEN_RATE_YELLOW_THRESHOLD < reopen_ratio <= REOPEN_RATE_RED_THRESHOLD
        ):
            threshold_pct = REOPEN_RATE_YELLOW_THRESHOLD * 100
            message = f"Reopen events per 100 eligible tickets: {reopen_rate_pct:.1f}% > {threshold_pct:.0f}%"
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

        hard_rule_signal = "RED" if red_details else "YELLOW" if yellow_details else "GREEN"
        if (
            scope_churn_7d_pct is None
            or reopen_rate_pct is None
            or median_cycle_time_days is None
        ):
            signal = "RED" if hard_rule_signal == "RED" else "INCONCLUSIVE"
        else:
            confidence_score = SignalService._compute_release_confidence_score(
                open_blockers=open_blockers,
                open_high_severity_bugs=open_high_severity_bugs,
                scope_churn_7d_pct=scope_churn_7d_pct,
                reopen_rate_pct=reopen_rate_pct,
                median_cycle_time_days=median_cycle_time_days,
            )
            confidence_signal = SignalService._signal_from_confidence_score(confidence_score)
            signal = SignalService._most_severe_signal(hard_rule_signal, confidence_signal)
        reasons = [*red_reasons, *yellow_reasons]
        details = [*red_details, *yellow_details]
        if not reasons:
            reasons = ["No major risk indicators"]

        return signal, reasons, details

    @staticmethod
    def _build_release_readiness_details(
        signal: str | None,
        open_blockers: int,
        open_high_severity_bugs: int,
        scope_churn_7d_pct: float | None,
        reopen_rate_pct: float | None,
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
            *(
                [
                    {
                        "metric_name": "scope_churn_7d_pct",
                        "label": f"Scope churn <= {scope_churn_red_pct:.0f}%",
                        "passed": scope_churn_7d_pct <= scope_churn_red_pct,
                        "value": scope_churn_7d_pct,
                        "comparison": "<=",
                        "threshold": float(scope_churn_red_pct),
                    }
                ]
                if scope_churn_7d_pct is not None
                else []
            ),
            *(
                [
                    {
                        "metric_name": "reopen_rate_pct",
                        "label": f"Reopen events per 100 eligible tickets <= {reopen_rate_red_pct:.0f}%",
                        "passed": reopen_rate_pct <= reopen_rate_red_pct,
                        "value": reopen_rate_pct,
                        "comparison": "<=",
                        "threshold": float(reopen_rate_red_pct),
                    }
                ]
                if reopen_rate_pct is not None
                else []
            ),
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

        risk_points = SignalService._compute_release_risk_points(
            open_blockers=open_blockers,
            open_high_severity_bugs=open_high_severity_bugs,
            scope_churn_7d_pct=scope_churn_7d_pct,
            reopen_rate_pct=reopen_rate_pct,
            median_cycle_time_days=median_cycle_time_days,
        )
        critical_risks: list[dict[str, object]] = []
        warnings: list[dict[str, object]] = []

        if open_blockers > OPEN_BLOCKERS_RED_THRESHOLD:
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
            warnings.append(
                {
                    "metric_name": "open_high_severity_bugs",
                    "level": "WARNING",
                    "message": f"{open_high_severity_bugs} high severity bug remains unresolved",
                    "value": open_high_severity_bugs,
                    "contribution_pct": 0.0,
                }
            )

        if scope_churn_7d_pct is not None and scope_churn_7d_pct > scope_churn_red_pct:
            warnings.append(
                {
                    "metric_name": "scope_churn_7d_pct",
                    "level": "WARNING",
                    "message": f"Scope churn increased to {scope_churn_7d_pct:.0f}%",
                    "value": scope_churn_7d_pct,
                    "contribution_pct": 0.0,
                }
            )
        elif scope_churn_7d_pct is not None and scope_churn_7d_pct > scope_churn_yellow_pct:
            warnings.append(
                {
                    "metric_name": "scope_churn_7d_pct",
                    "level": "WARNING",
                    "message": f"Scope churn increased to {scope_churn_7d_pct:.0f}%",
                    "value": scope_churn_7d_pct,
                    "contribution_pct": 0.0,
                }
            )

        if reopen_rate_pct is not None and reopen_rate_pct > reopen_rate_red_pct:
            warnings.append(
                {
                    "metric_name": "reopen_rate_pct",
                    "level": "WARNING",
                    "message": "Reopen events per 100 eligible tickets exceed target",
                    "value": reopen_rate_pct,
                    "contribution_pct": 0.0,
                }
            )
        elif reopen_rate_pct is not None and reopen_rate_pct > reopen_rate_yellow_pct:
            warnings.append(
                {
                    "metric_name": "reopen_rate_pct",
                    "level": "WARNING",
                    "message": "Reopen events per 100 eligible tickets exceed target",
                    "value": reopen_rate_pct,
                    "contribution_pct": 0.0,
                }
            )

        if median_cycle_time_days is not None and median_cycle_time_days > CYCLE_TIME_YELLOW_THRESHOLD_DAYS:
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
        confidence_score = (
            SignalService._compute_release_confidence_score(
                open_blockers=open_blockers,
                open_high_severity_bugs=open_high_severity_bugs,
                scope_churn_7d_pct=scope_churn_7d_pct,
                reopen_rate_pct=reopen_rate_pct,
                median_cycle_time_days=median_cycle_time_days,
            )
            if (
                scope_churn_7d_pct is not None
                and reopen_rate_pct is not None
                and median_cycle_time_days is not None
            )
            else None
        )
        computed_signal, _, _ = SignalService._evaluate_signal_with_details(
            open_blockers=open_blockers,
            open_high_severity_bugs=open_high_severity_bugs,
            scope_churn_7d_pct=scope_churn_7d_pct,
            reopen_rate_pct=reopen_rate_pct,
            median_cycle_time_days=median_cycle_time_days,
        )
        contribution_by_metric = {
            metric_name: round((points / total_risk_points) * 100, 1)
            for metric_name, points in risk_points.items()
        } if total_risk_points > 0 else {}

        for item in critical_risks + warnings:
            item["contribution_pct"] = contribution_by_metric.get(str(item["metric_name"]), 0.0)

        primary_risk = None
        if risk_points:
            primary_metric_name = max(
                risk_points,
                key=lambda metric_name: risk_points[metric_name],
            )
            label_by_metric = {
                "open_blockers": "Open blockers",
                "open_high_severity_bugs": "High severity bugs",
                "scope_churn_7d_pct": "Scope churn",
                "reopen_rate_pct": "Reopen events per 100 eligible tickets",
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
            "INCONCLUSIVE": "INCONCLUSIVE",
        }
        summaries = {
            "RED": "Current release confidence is in the red band.",
            "YELLOW": "Current release confidence is in the yellow band.",
            "GREEN": "Current release confidence is in the green band.",
            "INCONCLUSIVE": "Release status is inconclusive because required metric inputs are unavailable or incomplete.",
        }

        return {
            "signal": computed_signal,
            "status_label": status_labels[computed_signal],
            "confidence_score": confidence_score,
            "summary": summaries[computed_signal],
            "release_gates": gates,
            "critical_risks": critical_risks,
            "warnings": warnings,
            "primary_risk": primary_risk,
        }

    @staticmethod
    def _build_release_risk_aging(
        session: Session,
        release_id: str,
        as_of: datetime,
        open_blocker_issue_keys: list[str] | None = None,
        open_high_severity_bug_issue_keys: list[str] | None = None,
    ) -> dict[str, object]:
        """Build deterministic risk aging from current issue rows as of a snapshot timestamp."""
        field_mapper = JiraFieldMapper(get_settings())
        as_of_utc = _coerce_utc(as_of)

        blocker_issues = SignalService._list_risk_aging_issues(
            session=session,
            release_id=release_id,
            field_mapper=field_mapper,
            risk_type="blockers",
            issue_keys=open_blocker_issue_keys,
        )
        high_severity_bug_issues = SignalService._list_risk_aging_issues(
            session=session,
            release_id=release_id,
            field_mapper=field_mapper,
            risk_type="high_severity_bugs",
            issue_keys=open_high_severity_bug_issue_keys,
        )

        return {
            "blockers": SignalService._summarize_issue_risk_ages(
                session, blocker_issues, as_of_utc, field_mapper, "blockers"
            ),
            "high_severity_bugs": SignalService._summarize_issue_risk_ages(
                session, high_severity_bug_issues, as_of_utc, field_mapper, "high_severity_bugs"
            ),
            "as_of": as_of_utc,
        }

    @staticmethod
    def _build_last_24_hours(
        session: Session,
        release_id: str,
        latest_snapshot: MetricSnapshot,
    ) -> dict[str, object]:
        """Build deterministic deltas from latest snapshot against the 24h baseline snapshot."""
        latest_at = _coerce_utc(latest_snapshot.snapshot_at)
        baseline_snapshot = MetricRepository.get_latest_snapshot_at_or_before(
            session=session,
            release_id=release_id,
            snapshot_at=latest_at - timedelta(hours=24),
        )

        if baseline_snapshot is None:
            return {"as_of": latest_at, "baseline_at": None, "has_baseline": False, "unavailable_reason": None, "items": []}

        baseline_at = _coerce_utc(baseline_snapshot.snapshot_at)
        if latest_snapshot.ruleset_version != baseline_snapshot.ruleset_version:
            return {
                "as_of": latest_at,
                "baseline_at": baseline_at,
                "has_baseline": True,
                "unavailable_reason": "Snapshot comparison unavailable because ruleset versions differ.",
                "items": [],
            }
        if latest_snapshot.ruleset_version == 0:
            return {
                "as_of": latest_at,
                "baseline_at": baseline_at,
                "has_baseline": True,
                "unavailable_reason": "Derived legacy release confidence is unavailable because it was not stored at calculation time.",
                "items": [],
            }
        latest_confidence = SignalService._confidence_score_for_snapshot(latest_snapshot)
        baseline_confidence = SignalService._confidence_score_for_snapshot(baseline_snapshot)

        items = [
            SignalService._build_last_24_hours_item(
                metric_name="open_blockers",
                label="blocker",
                value_type="count",
                delta=SignalService._numeric_delta(latest_snapshot.open_blockers, baseline_snapshot.open_blockers),
                positive_when="decrease",
            ),
            SignalService._build_last_24_hours_item(
                metric_name="open_high_severity_bugs",
                label="high severity bug",
                value_type="count",
                delta=SignalService._numeric_delta(
                    latest_snapshot.open_high_severity_bugs,
                    baseline_snapshot.open_high_severity_bugs,
                ),
                positive_when="decrease",
            ),
            SignalService._build_last_24_hours_item(
                metric_name="completed_tickets",
                label="completed ticket",
                value_type="count",
                delta=SignalService._numeric_delta(
                    latest_snapshot.completed_tickets,
                    baseline_snapshot.completed_tickets,
                ),
                positive_when="increase",
            ),
            SignalService._build_last_24_hours_item(
                metric_name="confidence_score",
                label="Confidence",
                value_type="percentage",
                delta=SignalService._numeric_delta(latest_confidence, baseline_confidence),
                positive_when="increase",
            ),
        ]

        return {"as_of": latest_at, "baseline_at": baseline_at, "has_baseline": True, "unavailable_reason": None, "items": items}

    @staticmethod
    def _build_release_outlook(
        release_date: datetime | None,
        latest_snapshot: MetricSnapshot | None,
        final_signal: str | None,
        confidence_score: float | None,
        release_gates: list[dict[str, object]],
        critical_risks: list[dict[str, object]],
        warnings: list[dict[str, object]],
        last_24_hours: dict[str, object],
    ) -> dict[str, object]:
        """Summarize current stored release evidence without forecasting."""
        label_by_signal = {
            "GREEN": "ON TRACK",
            "YELLOW": "NEEDS ATTENTION",
            "RED": "AT RISK",
            "INCONCLUSIVE": "INCONCLUSIVE",
        }
        snapshot_at = (
            _coerce_utc(latest_snapshot.snapshot_at) if latest_snapshot is not None else None
        )
        release_date_utc = _coerce_utc(release_date) if release_date is not None else None
        days_remaining = (
            (release_date_utc.date() - snapshot_at.date()).days
            if release_date_utc is not None and snapshot_at is not None
            else None
        )
        confidence_change_24h = None
        last_24_hour_items = cast(
            list[dict[str, object]],
            last_24_hours.get("items", []),
        )
        for item in last_24_hour_items:
            if isinstance(item, dict) and item.get("metric_name") == "confidence_score":
                confidence_change_24h = item.get("delta")
                break

        active_conditions = [*critical_risks, *warnings]
        return {
            "label": (
                label_by_signal.get(final_signal, "NOT COMPUTED")
                if final_signal is not None
                else "NOT COMPUTED"
            ),
            "signal": final_signal,
            "confidence_score": confidence_score,
            "snapshot_at": snapshot_at,
            "release_date": release_date_utc,
            "days_remaining": days_remaining,
            "passed_gate_count": sum(1 for gate in release_gates if gate.get("passed") is True),
            "failed_gate_count": sum(1 for gate in release_gates if gate.get("passed") is False),
            "release_gates": release_gates,
            "confidence_change_24h": confidence_change_24h,
            "confidence_baseline_at": last_24_hours.get("baseline_at"),
            "active_conditions": active_conditions,
            "disclaimer": RELEASE_OUTLOOK_DISCLAIMER,
        }

    @staticmethod
    def _confidence_score_for_snapshot(snapshot: MetricSnapshot) -> float | None:
        return snapshot.confidence_score if snapshot.ruleset_version > 0 else None

    @staticmethod
    def _numeric_delta(latest_value: int | float | None, baseline_value: int | float | None) -> float | None:
        if latest_value is None or baseline_value is None:
            return None
        return round(float(latest_value) - float(baseline_value), 1)

    @staticmethod
    def _build_last_24_hours_item(
        metric_name: str,
        label: str,
        value_type: str,
        delta: float | None,
        positive_when: str,
    ) -> dict[str, str | float | None]:
        impact = "unknown"
        if delta == 0:
            impact = "neutral"
        elif delta is not None:
            increased = delta > 0
            if positive_when == "increase":
                impact = "positive" if increased else "negative"
            elif positive_when == "decrease":
                impact = "negative" if increased else "positive"

        return {
            "metric_name": metric_name,
            "label": label,
            "delta": delta,
            "value_type": value_type,
            "impact": impact,
        }

    @staticmethod
    def _list_risk_aging_issues(
        session: Session,
        release_id: str,
        field_mapper: JiraFieldMapper,
        risk_type: str,
        issue_keys: list[str] | None,
    ) -> list[Issue]:
        if issue_keys is not None:
            if not issue_keys:
                return []

            return list(
                session.scalars(
                    select(Issue)
                    .where(Issue.release_id == release_id, Issue.issue_key.in_(issue_keys))
                    .order_by(Issue.issue_key)
                ).all()
            )

        if risk_type == "blockers":
            issues = session.scalars(
                select(Issue).where(Issue.release_id == release_id).order_by(Issue.issue_key)
            ).all()
            return [
                issue
                for issue in issues
                if field_mapper.classify_blocker(
                    issue_type=issue.issue_type,
                    severity=issue.priority,
                    status=issue.status,
                    blocker_flag=issue.jira_blocker_flag,
                )
            ]

        if risk_type == "high_severity_bugs":
            return list(
                session.scalars(
                    select(Issue)
                    .where(
                        Issue.release_id == release_id,
                        func.lower(Issue.issue_type).in_(field_mapper.bug_issue_types),
                        func.lower(Issue.priority).in_(field_mapper.high_severity_values),
                        func.lower(Issue.status).not_in(field_mapper.done_statuses),
                    )
                    .order_by(Issue.issue_key)
                ).all()
            )

        raise ValueError(f"Unknown risk aging type: {risk_type!r}")

    @staticmethod
    def _summarize_issue_risk_ages(
        session: Session,
        issues: list[Issue],
        as_of: datetime,
        field_mapper: JiraFieldMapper,
        risk_type: str,
    ) -> dict[str, object]:
        if not issues:
            return {
                "count": 0,
                "known_count": 0,
                "unknown_count": 0,
                "oldest_age_days": None,
                "average_age_days": None,
                "tickets": [],
            }

        tickets: list[dict[str, object]] = []
        ages: list[float] = []
        for issue in issues:
            risk_start = SignalService._risk_start_evidence(
                session=session,
                issue=issue,
                as_of=as_of,
                field_mapper=field_mapper,
                risk_type=risk_type,
            )
            risk_started_at = risk_start["risk_started_at"]
            age_days = (
                None
                if risk_started_at is None
                else round(max(0.0, (as_of - risk_started_at).total_seconds()) / 86400.0, 1)
            )
            if age_days is not None:
                ages.append(age_days)
            jira_created_at = (
                _coerce_utc(issue.jira_created_at) if issue.jira_created_at is not None else None
            )
            issue_age_days = (
                round(max(0.0, (as_of - jira_created_at).total_seconds()) / 86400.0, 1)
                if jira_created_at is not None
                else None
            )
            tickets.append(
                {
                    "key": issue.issue_key,
                    "age_days": age_days,
                    "issue_age_days": issue_age_days,
                    "jira_created_at": jira_created_at,
                    "risk_started_at": risk_started_at,
                    "risk_start_source_field": risk_start["source_field"],
                    "risk_start_source_changed_at": risk_start["source_changed_at"],
                    "history_complete": issue.jira_changelog_complete,
                    "explanation": (
                        None
                        if age_days is not None
                        else "Risk start unavailable from Jira history."
                    ),
                }
            )
        return {
            "count": len(issues),
            "known_count": len(ages),
            "unknown_count": len(issues) - len(ages),
            "oldest_age_days": round(max(ages), 1) if ages else None,
            "average_age_days": round(sum(ages) / len(ages), 1) if ages else None,
            "tickets": tickets,
        }

    @staticmethod
    def _risk_start_evidence(
        session: Session,
        issue: Issue,
        as_of: datetime,
        field_mapper: JiraFieldMapper,
        risk_type: str,
    ) -> _RiskStartEvidence:
        if not issue.jira_changelog_complete:
            return {"risk_started_at": None, "source_field": None, "source_changed_at": None}

        current_blocker_flag = issue.jira_blocker_flag
        state: dict[str, object] = {
            "status": issue.status,
            "priority": issue.priority,
            "issue_type": issue.issue_type,
            "blocker_flag": current_blocker_flag,
        }

        def is_active() -> bool:
            if risk_type == "blockers":
                return field_mapper.classify_blocker(
                    issue_type=str(state["issue_type"] or ""),
                    severity=str(state["priority"]) if state["priority"] is not None else None,
                    status=str(state["status"] or ""),
                    blocker_flag=(
                        state["blocker_flag"]
                        if isinstance(state["blocker_flag"], bool)
                        else None
                    ),
                )
            if risk_type == "high_severity_bugs":
                return (
                    field_mapper.is_bug(str(state["issue_type"] or ""))
                    and field_mapper.is_high_severity(
                        str(state["priority"]) if state["priority"] is not None else None
                    )
                    and not field_mapper.is_done_status(str(state["status"] or ""))
                )
            raise ValueError(f"Unknown risk aging type: {risk_type!r}")

        history = session.scalars(
            select(IssueHistory)
            .where(IssueHistory.issue_key == issue.issue_key, IssueHistory.changed_at <= as_of)
            .order_by(IssueHistory.changed_at.desc(), IssueHistory.id.desc())
        ).all()
        severity_fields = {"priority", field_mapper.mapping.severity_field.casefold()}
        blocker_field = field_mapper.mapping.blocker_field.casefold()
        for entry in history:
            field_name = entry.field_name.strip().casefold()
            if field_name == "status":
                state["status"] = entry.old_value
            elif field_name in severity_fields:
                state["priority"] = entry.old_value
            elif field_name in {"issuetype", "issue type"}:
                state["issue_type"] = entry.old_value
            elif blocker_field and field_name == blocker_field:
                state["blocker_flag"] = field_mapper.parse_blocker_flag(entry.old_value)
            else:
                continue
            if not is_active():
                changed_at = _coerce_utc(entry.changed_at)
                return {
                    "risk_started_at": changed_at,
                    "source_field": entry.field_name,
                    "source_changed_at": changed_at,
                }

        jira_created_at = (
            _coerce_utc(issue.jira_created_at) if issue.jira_created_at is not None else None
        )
        if is_active() and jira_created_at is not None and jira_created_at <= as_of:
            return {
                "risk_started_at": jira_created_at,
                "source_field": "jira_created_at",
                "source_changed_at": jira_created_at,
            }
        return {"risk_started_at": None, "source_field": None, "source_changed_at": None}

    @staticmethod
    def _evaluate_signal(
        open_blockers: int,
        open_high_severity_bugs: int,
        scope_churn_7d_pct: float,
        reopen_rate_pct: float,
        median_cycle_time_days: float | None,
    ) -> tuple[str, list[str]]:
        """
        Apply deterministic hard rules and confidence-score bands.

        Metric thresholds determine hard-rule severity, risk points, and reasons.
        The final signal is the more severe of the hard-rule result and confidence
        score band.

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
