from dataclasses import dataclass
from typing import Any

from app.schemas.drivers import DriverAnalysis
from app.services.analytics_service import DELIVERY_CONFIDENCE_WEIGHTS
from app.services.signal_service import SignalService


@dataclass(frozen=True)
class _DriverCandidate:
    key: str
    title: str
    category: str
    impact: float
    explanation: str
    recommendation: str


class DriverAnalysisService:
    """Identify the largest deterministic confidence drag for releases and sprints."""

    RELEASE_DRIVER_DETAILS = {
        "open_blockers": (
            "Open Blockers",
            "Risk",
            "Open blockers are consuming the largest share of release confidence.",
            "Resolve or explicitly de-scope blocker tickets before moving the release forward.",
        ),
        "open_high_severity_bugs": (
            "High Severity Bugs",
            "Quality",
            "Open high-severity bugs are the largest quality drag on release confidence.",
            "Prioritize high-severity bug fixes and verify them before release approval.",
        ),
        "scope_churn_7d_pct": (
            "Scope Churn",
            "Delivery",
            "Recent fix-version movement is the largest source of release risk.",
            "Stabilize the release scope and defer non-critical fix-version changes.",
        ),
        "reopen_rate_pct": (
            "Reopen Events per 100 Eligible Tickets",
            "Quality",
            "Reopened work is the largest drag on release confidence.",
            "Review reopened tickets for common acceptance or quality gaps and close the loop before release.",
        ),
        "median_cycle_time_days": (
            "Cycle Time",
            "Flow",
            "Cycle time is the largest flow drag on release confidence.",
            "Reduce aging in-progress work and focus the team on finishing active tickets.",
        ),
    }
    RELEASE_DRIVER_ORDER = [
        "open_blockers",
        "open_high_severity_bugs",
        "scope_churn_7d_pct",
        "reopen_rate_pct",
        "median_cycle_time_days",
    ]

    SPRINT_DRIVER_DETAILS = {
        "progress_alignment": (
            "Progress Alignment",
            "Delivery",
            "Completed work is the largest drag against expected sprint progress.",
            "Refocus on finishing committed work that is closest to done.",
        ),
        "velocity_fit": (
            "Velocity Fit",
            "Delivery",
            "Remaining work versus historical velocity is the largest delivery drag.",
            "Rebalance remaining work against available capacity and de-scope lower priority items if needed.",
        ),
        "scope_stability": (
            "Scope Stability",
            "Delivery",
            "Post-start scope movement is the largest drag on delivery confidence.",
            "Freeze sprint scope where possible and move new requests into the next planning cycle.",
        ),
        "blocker_penalty": (
            "Blocker Health",
            "Risk",
            "Open blockers are the largest drag on sprint delivery confidence.",
            "Clear blocker ownership and resolve blocked tickets before pulling more work.",
        ),
    }
    SPRINT_DRIVER_ORDER = [
        "progress_alignment",
        "velocity_fit",
        "scope_stability",
        "blocker_penalty",
    ]

    @staticmethod
    def build_release_driver(snapshot: Any) -> DriverAnalysis:
        risk_points = SignalService._compute_release_risk_points(
            open_blockers=snapshot.open_blockers,
            open_high_severity_bugs=snapshot.open_high_severity_bugs,
            scope_churn_7d_pct=snapshot.scope_churn_7d_pct,
            reopen_rate_pct=snapshot.reopen_rate_pct,
            median_cycle_time_days=snapshot.median_cycle_time_days,
        )
        candidates = [
            DriverAnalysisService._release_candidate(metric_name, risk_points[metric_name])
            for metric_name in DriverAnalysisService.RELEASE_DRIVER_ORDER
            if metric_name in risk_points
        ]
        if not candidates:
            return DriverAnalysisService._empty_release_driver()

        total_loss = sum(abs(candidate.impact) for candidate in candidates)
        return DriverAnalysisService._build_result(candidates=candidates, total_loss=total_loss)

    @staticmethod
    def build_sprint_driver(
        score: float,
        components: dict[str, float],
    ) -> DriverAnalysis:
        candidates = [
            DriverAnalysisService._sprint_candidate(component_name, components[component_name])
            for component_name in DriverAnalysisService.SPRINT_DRIVER_ORDER
            if component_name in components
        ]
        candidates = [candidate for candidate in candidates if candidate.impact < 0.0]
        if not candidates:
            return DriverAnalysisService._empty_sprint_driver()

        _ = score
        total_loss = sum(abs(candidate.impact) for candidate in candidates)
        return DriverAnalysisService._build_result(candidates=candidates, total_loss=total_loss)

    @staticmethod
    def _release_candidate(metric_name: str, points: float) -> _DriverCandidate:
        title, category, explanation, recommendation = DriverAnalysisService.RELEASE_DRIVER_DETAILS[metric_name]
        return _DriverCandidate(
            key=metric_name,
            title=title,
            category=category,
            impact=round(-points, 2),
            explanation=explanation,
            recommendation=recommendation,
        )

    @staticmethod
    def _sprint_candidate(component_name: str, score: float) -> _DriverCandidate:
        title, category, explanation, recommendation = DriverAnalysisService.SPRINT_DRIVER_DETAILS[component_name]
        weight = DELIVERY_CONFIDENCE_WEIGHTS[component_name]
        impact = -round(max(0.0, 100.0 - score) * weight, 2)
        return _DriverCandidate(
            key=component_name,
            title=title,
            category=category,
            impact=impact,
            explanation=explanation,
            recommendation=recommendation,
        )

    @staticmethod
    def _build_result(candidates: list[_DriverCandidate], total_loss: float) -> DriverAnalysis:
        selected = min(
            candidates,
            key=lambda candidate: (
                candidate.impact,
                DriverAnalysisService._driver_sort_index(candidate.key),
            ),
        )
        contribution = 0.0 if total_loss <= 0.0 else round((abs(selected.impact) / total_loss) * 100.0, 1)
        return DriverAnalysis(
            title=selected.title,
            category=selected.category,
            impact=selected.impact,
            contributionPercent=contribution,
            explanation=selected.explanation,
            recommendation=selected.recommendation,
        )

    @staticmethod
    def _driver_sort_index(key: str) -> int:
        combined_order = DriverAnalysisService.RELEASE_DRIVER_ORDER + DriverAnalysisService.SPRINT_DRIVER_ORDER
        return combined_order.index(key) if key in combined_order else len(combined_order)

    @staticmethod
    def _empty_release_driver() -> DriverAnalysis:
        return DriverAnalysis(
            title="No Confidence Drag",
            category="None",
            impact=0.0,
            contributionPercent=0.0,
            explanation="No active release risk points are reducing confidence.",
            recommendation="Maintain release readiness by keeping blockers, quality risk, scope churn, and flow within thresholds.",
        )

    @staticmethod
    def _empty_sprint_driver() -> DriverAnalysis:
        return DriverAnalysis(
            title="No Delivery Drag",
            category="None",
            impact=0.0,
            contributionPercent=0.0,
            explanation="No delivery confidence component is currently reducing the sprint score.",
            recommendation="Maintain the current delivery posture and continue monitoring progress, velocity, blockers, and scope stability.",
        )
