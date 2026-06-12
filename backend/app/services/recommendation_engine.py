from dataclasses import dataclass
from typing import Any

from app.schemas.recommendations import RecommendationAction, RecommendationEffort
from app.utils.constants import (
    CYCLE_TIME_YELLOW_THRESHOLD_DAYS,
    HIGH_SEVERITY_BUGS_YELLOW_THRESHOLD,
    OPEN_BLOCKERS_RED_THRESHOLD,
    REOPEN_RATE_YELLOW_THRESHOLD,
    SCOPE_CHURN_YELLOW_THRESHOLD,
)


@dataclass(frozen=True)
class _RecommendationRule:
    key: str
    title: str
    description: str
    confidence_impact: int
    effort: RecommendationEffort
    category: str


class RecommendationEngine:
    """Convert deterministic metrics into prioritized recommended actions."""

    RELEASE_RULES = {
        "open_blockers": _RecommendationRule(
            key="open_blockers",
            title="Resolve blockers",
            description="Resolve or explicitly de-scope open blocker tickets before moving the release forward.",
            confidence_impact=10,
            effort="high",
            category="Risk",
        ),
        "open_high_severity_bugs": _RecommendationRule(
            key="open_high_severity_bugs",
            title="Resolve critical defects",
            description="Prioritize high-severity defect fixes and verify them before release approval.",
            confidence_impact=8,
            effort="medium",
            category="Quality",
        ),
        "scope_churn_7d_pct": _RecommendationRule(
            key="scope_churn_7d_pct",
            title="Stabilize release scope",
            description="Stop non-critical fix-version movement and defer new scope to a later release.",
            confidence_impact=7,
            effort="medium",
            category="Delivery",
        ),
        "reopen_rate_pct": _RecommendationRule(
            key="reopen_rate_pct",
            title="Reduce reopen rate",
            description="Review reopened tickets for acceptance or quality gaps and close the loop before release.",
            confidence_impact=6,
            effort="medium",
            category="Quality",
        ),
        "median_cycle_time_days": _RecommendationRule(
            key="median_cycle_time_days",
            title="Reduce cycle time",
            description="Focus the team on aging in-progress work before starting additional release scope.",
            confidence_impact=4,
            effort="low",
            category="Flow",
        ),
    }
    RELEASE_ORDER = [
        "open_blockers",
        "open_high_severity_bugs",
        "scope_churn_7d_pct",
        "reopen_rate_pct",
        "median_cycle_time_days",
    ]

    SPRINT_RULES = {
        "scope_stability": _RecommendationRule(
            key="scope_stability",
            title="Reduce scope changes",
            description="Freeze sprint scope where possible and move new requests into the next planning cycle.",
            confidence_impact=7,
            effort="low",
            category="Delivery",
        ),
        "open_blockers": _RecommendationRule(
            key="open_blockers",
            title="Resolve sprint blockers",
            description="Assign clear ownership to blocked tickets and clear them before pulling more work.",
            confidence_impact=6,
            effort="high",
            category="Risk",
        ),
        "progress_alignment": _RecommendationRule(
            key="progress_alignment",
            title="Complete committed work",
            description="Refocus on finishing committed work that is closest to done.",
            confidence_impact=5,
            effort="medium",
            category="Delivery",
        ),
        "open_high_severity_bugs": _RecommendationRule(
            key="open_high_severity_bugs",
            title="Resolve sprint defects",
            description="Prioritize high-severity sprint defects before adding more in-progress work.",
            confidence_impact=5,
            effort="medium",
            category="Quality",
        ),
        "workload_concentration": _RecommendationRule(
            key="workload_concentration",
            title="Reduce workload concentration",
            description="Rebalance active work so no single assignee owns more than the workload concentration threshold.",
            confidence_impact=4,
            effort="medium",
            category="Risk",
        ),
        "median_cycle_time_days": _RecommendationRule(
            key="median_cycle_time_days",
            title="Reduce sprint cycle time",
            description="Finish aging active work before starting additional sprint items.",
            confidence_impact=4,
            effort="low",
            category="Flow",
        ),
        "reopen_rate_pct": _RecommendationRule(
            key="reopen_rate_pct",
            title="Reduce reopened sprint work",
            description="Review reopened sprint work for recurring quality or acceptance gaps.",
            confidence_impact=4,
            effort="medium",
            category="Quality",
        ),
    }
    SPRINT_ORDER = [
        "scope_stability",
        "open_blockers",
        "progress_alignment",
        "open_high_severity_bugs",
        "workload_concentration",
        "median_cycle_time_days",
        "reopen_rate_pct",
    ]

    WORKLOAD_CONCENTRATION_YELLOW_PCT = 35.0

    @staticmethod
    def build_release_recommendations(snapshot: Any) -> list[RecommendationAction]:
        candidates: list[_RecommendationRule] = []
        if snapshot.open_blockers > OPEN_BLOCKERS_RED_THRESHOLD:
            candidates.append(RecommendationEngine.RELEASE_RULES["open_blockers"])
        if snapshot.open_high_severity_bugs > HIGH_SEVERITY_BUGS_YELLOW_THRESHOLD:
            candidates.append(RecommendationEngine.RELEASE_RULES["open_high_severity_bugs"])
        if snapshot.scope_churn_7d_pct > SCOPE_CHURN_YELLOW_THRESHOLD * 100:
            candidates.append(RecommendationEngine.RELEASE_RULES["scope_churn_7d_pct"])
        if snapshot.reopen_rate_pct > REOPEN_RATE_YELLOW_THRESHOLD * 100:
            candidates.append(RecommendationEngine.RELEASE_RULES["reopen_rate_pct"])
        if (
            snapshot.median_cycle_time_days is not None
            and snapshot.median_cycle_time_days > CYCLE_TIME_YELLOW_THRESHOLD_DAYS
        ):
            candidates.append(RecommendationEngine.RELEASE_RULES["median_cycle_time_days"])
        return RecommendationEngine._prioritize(candidates, RecommendationEngine.RELEASE_ORDER)

    @staticmethod
    def build_sprint_recommendations(
        snapshot: Any,
        sprint_issues: list[Any] | None = None,
    ) -> list[RecommendationAction]:
        candidates: list[_RecommendationRule] = []
        components = snapshot.delivery_confidence_components or {}
        inputs = snapshot.delivery_confidence_inputs or {}

        if int(inputs.get("scope_change_count") or 0) > 0 or float(components.get("scope_stability", 100.0)) < 100.0:
            candidates.append(RecommendationEngine.SPRINT_RULES["scope_stability"])
        if snapshot.open_blockers > OPEN_BLOCKERS_RED_THRESHOLD:
            candidates.append(RecommendationEngine.SPRINT_RULES["open_blockers"])
        if (
            snapshot.completed_scope_pct < 100.0
            or float(inputs.get("remaining_effective_points") or 0.0) > 0.0
            or float(components.get("progress_alignment", 100.0)) < 100.0
        ):
            candidates.append(RecommendationEngine.SPRINT_RULES["progress_alignment"])
        if snapshot.open_high_severity_bugs > HIGH_SEVERITY_BUGS_YELLOW_THRESHOLD:
            candidates.append(RecommendationEngine.SPRINT_RULES["open_high_severity_bugs"])
        if RecommendationEngine._has_workload_concentration_risk(sprint_issues or []):
            candidates.append(RecommendationEngine.SPRINT_RULES["workload_concentration"])
        if (
            snapshot.median_cycle_time_days is not None
            and snapshot.median_cycle_time_days > CYCLE_TIME_YELLOW_THRESHOLD_DAYS
        ):
            candidates.append(RecommendationEngine.SPRINT_RULES["median_cycle_time_days"])
        if snapshot.reopen_rate_pct > REOPEN_RATE_YELLOW_THRESHOLD * 100:
            candidates.append(RecommendationEngine.SPRINT_RULES["reopen_rate_pct"])
        return RecommendationEngine._prioritize(candidates, RecommendationEngine.SPRINT_ORDER)

    @staticmethod
    def _prioritize(
        candidates: list[_RecommendationRule],
        rule_order: list[str],
    ) -> list[RecommendationAction]:
        ordered = sorted(
            candidates,
            key=lambda item: (
                -item.confidence_impact,
                rule_order.index(item.key) if item.key in rule_order else len(rule_order),
            ),
        )
        return [
            RecommendationAction(
                title=item.title,
                description=item.description,
                priority=index + 1,
                confidenceImpact=item.confidence_impact,
                effort=item.effort,
                category=item.category,
            )
            for index, item in enumerate(ordered)
        ]

    @staticmethod
    def _has_workload_concentration_risk(sprint_issues: list[Any]) -> bool:
        active_points_by_assignee: dict[str, float] = {}
        total_active_points = 0.0
        for issue in sprint_issues:
            if RecommendationEngine._is_done_status(str(getattr(issue, "status", ""))):
                continue
            points = RecommendationEngine._effective_points(getattr(issue, "story_points", None))
            assignee = str(getattr(issue, "assignee", None) or "Unassigned")
            active_points_by_assignee[assignee] = active_points_by_assignee.get(assignee, 0.0) + points
            total_active_points += points

        if total_active_points <= 0.0:
            return False
        top_assignee_pct = max(active_points_by_assignee.values()) / total_active_points * 100.0
        return top_assignee_pct >= RecommendationEngine.WORKLOAD_CONCENTRATION_YELLOW_PCT

    @staticmethod
    def _effective_points(value: float | int | None) -> float:
        if value is None:
            return 1.0
        points = float(value)
        return points if points > 0 else 1.0

    @staticmethod
    def _is_done_status(status: str) -> bool:
        return status.strip().casefold() in {"done", "closed", "resolved"}
