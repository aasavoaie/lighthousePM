from typing import Any

from app.schemas.confidence import ConfidenceBreakdown, ConfidenceBreakdownComponent, ConfidenceStatus
from app.services.signal_service import SignalService
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


class ConfidenceBreakdownService:
    """Build deterministic explanations for release and sprint confidence scores."""

    RELEASE_COMPONENT_MAX = {
        "delivery": 30.0,
        "quality": 30.0,
        "flow": 20.0,
        "risk": 20.0,
    }

    @staticmethod
    def build_release_breakdown(snapshot: Any) -> ConfidenceBreakdown:
        risk_points = SignalService._compute_release_risk_points(
            open_blockers=snapshot.open_blockers,
            open_high_severity_bugs=snapshot.open_high_severity_bugs,
            scope_churn_7d_pct=snapshot.scope_churn_7d_pct,
            reopen_rate_pct=snapshot.reopen_rate_pct,
            median_cycle_time_days=snapshot.median_cycle_time_days,
        )
        blocker_points = risk_points.get("open_blockers", 0.0)
        penalties = {
            "delivery": risk_points.get("scope_churn_7d_pct", 0.0) + max(0.0, blocker_points - 20.0),
            "quality": risk_points.get("open_high_severity_bugs", 0.0) + risk_points.get("reopen_rate_pct", 0.0),
            "flow": risk_points.get("median_cycle_time_days", 0.0),
            "risk": min(blocker_points, 20.0),
        }
        components = [
            ConfidenceBreakdownService._release_component(
                component_id="delivery",
                name="Delivery",
                score=ConfidenceBreakdownService.RELEASE_COMPONENT_MAX["delivery"] - penalties["delivery"],
                max_score=ConfidenceBreakdownService.RELEASE_COMPONENT_MAX["delivery"],
                explanation=ConfidenceBreakdownService._release_delivery_explanation(snapshot),
            ),
            ConfidenceBreakdownService._release_component(
                component_id="quality",
                name="Quality",
                score=ConfidenceBreakdownService.RELEASE_COMPONENT_MAX["quality"] - penalties["quality"],
                max_score=ConfidenceBreakdownService.RELEASE_COMPONENT_MAX["quality"],
                explanation=ConfidenceBreakdownService._release_quality_explanation(snapshot),
            ),
            ConfidenceBreakdownService._release_component(
                component_id="flow",
                name="Flow",
                score=ConfidenceBreakdownService.RELEASE_COMPONENT_MAX["flow"] - penalties["flow"],
                max_score=ConfidenceBreakdownService.RELEASE_COMPONENT_MAX["flow"],
                explanation=ConfidenceBreakdownService._release_flow_explanation(snapshot),
            ),
            ConfidenceBreakdownService._release_component(
                component_id="risk",
                name="Risk",
                score=ConfidenceBreakdownService.RELEASE_COMPONENT_MAX["risk"] - penalties["risk"],
                max_score=ConfidenceBreakdownService.RELEASE_COMPONENT_MAX["risk"],
                explanation=ConfidenceBreakdownService._release_risk_explanation(snapshot),
            ),
        ]
        return ConfidenceBreakdown(
            totalScore=round(sum(component.score for component in components), 1),
            components=components,
        )

    @staticmethod
    def build_sprint_breakdown(
        score: float,
        components: dict[str, float],
        inputs: dict[str, Any] | None = None,
    ) -> ConfidenceBreakdown:
        inputs = inputs or {}
        ordered_components = [
            (
                "progress_alignment",
                "Progress Alignment",
                components["progress_alignment"],
                ConfidenceBreakdownService._sprint_progress_explanation(components["progress_alignment"], inputs),
            ),
            (
                "velocity_fit",
                "Velocity Fit",
                components["velocity_fit"],
                ConfidenceBreakdownService._sprint_velocity_explanation(components["velocity_fit"], inputs),
            ),
            (
                "scope_stability",
                "Scope Stability",
                components["scope_stability"],
                ConfidenceBreakdownService._sprint_scope_explanation(components["scope_stability"], inputs),
            ),
            (
                "blocker_health",
                "Blocker Health",
                components["blocker_penalty"],
                ConfidenceBreakdownService._sprint_blocker_explanation(components["blocker_penalty"], inputs),
            ),
        ]
        return ConfidenceBreakdown(
            totalScore=round(score, 2),
            components=[
                ConfidenceBreakdownComponent(
                    id=component_id,
                    name=name,
                    score=round(component_score, 2),
                    maxScore=100.0,
                    status=ConfidenceBreakdownService._status_for_ratio(component_score, 100.0),
                    explanation=explanation,
                )
                for component_id, name, component_score, explanation in ordered_components
            ],
        )

    @staticmethod
    def _release_component(
        component_id: str,
        name: str,
        score: float,
        max_score: float,
        explanation: str,
    ) -> ConfidenceBreakdownComponent:
        bounded_score = round(max(0.0, min(score, max_score)), 1)
        return ConfidenceBreakdownComponent(
            id=component_id,
            name=name,
            score=bounded_score,
            maxScore=max_score,
            status=ConfidenceBreakdownService._status_for_ratio(bounded_score, max_score),
            explanation=explanation,
        )

    @staticmethod
    def _status_for_ratio(score: float, max_score: float) -> ConfidenceStatus:
        ratio = 0.0 if max_score == 0 else score / max_score
        if ratio >= 0.9:
            return "good"
        if ratio >= 0.75:
            return "warning"
        return "critical"

    @staticmethod
    def _release_delivery_explanation(snapshot: Any) -> str:
        churn_yellow_pct = SCOPE_CHURN_YELLOW_THRESHOLD * 100
        churn_red_pct = SCOPE_CHURN_RED_THRESHOLD * 100
        if snapshot.open_blockers > OPEN_BLOCKERS_RED_THRESHOLD and snapshot.scope_churn_7d_pct > churn_red_pct:
            return "Open blockers and red-level scope churn are reducing delivery confidence."
        if snapshot.open_blockers > OPEN_BLOCKERS_RED_THRESHOLD:
            return "Open blockers reduce delivery confidence because blocked work can delay release completion."
        if snapshot.scope_churn_7d_pct > churn_red_pct:
            return f"Scope churn is above the red threshold ({snapshot.scope_churn_7d_pct:.1f}% > {churn_red_pct:.1f}%)."
        if snapshot.scope_churn_7d_pct > churn_yellow_pct:
            return f"Scope churn is above the warning threshold ({snapshot.scope_churn_7d_pct:.1f}% > {churn_yellow_pct:.1f}%)."
        return "Scope churn and blocker impact are within delivery confidence thresholds."

    @staticmethod
    def _release_quality_explanation(snapshot: Any) -> str:
        reopen_yellow_pct = REOPEN_RATE_YELLOW_THRESHOLD * 100
        reopen_red_pct = REOPEN_RATE_RED_THRESHOLD * 100
        if snapshot.open_high_severity_bugs > HIGH_SEVERITY_BUGS_RED_THRESHOLD:
            return f"{snapshot.open_high_severity_bugs} open high-severity bugs exceed the red quality threshold."
        if snapshot.open_high_severity_bugs > HIGH_SEVERITY_BUGS_YELLOW_THRESHOLD:
            return f"{snapshot.open_high_severity_bugs} open high-severity bug is reducing quality confidence."
        if snapshot.reopen_rate_pct > reopen_red_pct:
            return f"Reopen rate is above the red threshold ({snapshot.reopen_rate_pct:.1f}% > {reopen_red_pct:.1f}%)."
        if snapshot.reopen_rate_pct > reopen_yellow_pct:
            return f"Reopen rate is above the warning threshold ({snapshot.reopen_rate_pct:.1f}% > {reopen_yellow_pct:.1f}%)."
        return "High-severity bugs and reopen rate are within quality confidence thresholds."

    @staticmethod
    def _release_flow_explanation(snapshot: Any) -> str:
        if snapshot.median_cycle_time_days is None:
            return "Cycle time has no completed-work baseline yet, so flow confidence is not penalized."
        if snapshot.median_cycle_time_days > CYCLE_TIME_YELLOW_THRESHOLD_DAYS:
            return (
                f"Median cycle time is above the warning threshold "
                f"({snapshot.median_cycle_time_days:.1f}d > {CYCLE_TIME_YELLOW_THRESHOLD_DAYS:.1f}d)."
            )
        return "Median cycle time is within the flow confidence threshold."

    @staticmethod
    def _release_risk_explanation(snapshot: Any) -> str:
        if snapshot.open_blockers > OPEN_BLOCKERS_RED_THRESHOLD:
            issue_label = "issue is" if snapshot.open_blockers == 1 else "issues are"
            return f"{snapshot.open_blockers} open blocker {issue_label} consuming release risk capacity."
        return "No open blockers are consuming release risk capacity."

    @staticmethod
    def _sprint_progress_explanation(score: float, inputs: dict[str, Any]) -> str:
        elapsed = inputs.get("time_elapsed_pct")
        completed = inputs.get("completed_scope_pct")
        if elapsed is None:
            return "Sprint progress has no elapsed-time baseline, so progress alignment uses completed scope."
        if completed is None:
            return "Sprint progress has an elapsed-time baseline but no completed-scope value."
        if score >= 90:
            return f"Completed scope is aligned with elapsed sprint time ({completed:.1f}% done vs {elapsed:.1f}% elapsed)."
        return f"Completed scope is behind elapsed sprint time ({completed:.1f}% done vs {elapsed:.1f}% elapsed)."

    @staticmethod
    def _sprint_velocity_explanation(score: float, inputs: dict[str, Any]) -> str:
        historical_velocity = inputs.get("historical_velocity")
        if historical_velocity is None:
            return "No closed-sprint velocity baseline is available, so velocity fit is scored conservatively."
        if score >= 90:
            return "Remaining work fits within the historical velocity baseline."
        return "Remaining work is high relative to the historical velocity baseline."

    @staticmethod
    def _sprint_scope_explanation(score: float, inputs: dict[str, Any]) -> str:
        change_count = int(inputs.get("scope_change_count", 0))
        if change_count == 0:
            return "No post-start sprint scope changes were detected."
        if score >= 75:
            return f"{change_count} post-start scope changes were detected, within stability thresholds."
        return f"{change_count} post-start scope changes are reducing scope stability."

    @staticmethod
    def _sprint_blocker_explanation(score: float, inputs: dict[str, Any]) -> str:
        blocked_ratio = float(inputs.get("blocked_issue_ratio", 0.0))
        if blocked_ratio == 0:
            return "No open blockers are affecting sprint blocker health."
        if score >= 75:
            return f"Open blockers affect {blocked_ratio * 100:.1f}% of committed sprint issues."
        return f"Open blockers affect {blocked_ratio * 100:.1f}% of committed sprint issues and reduce confidence."
