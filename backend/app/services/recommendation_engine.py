from dataclasses import dataclass
from typing import Any, cast

from app.metric_catalog import metric_threshold_value
from app.schemas.availability import MetricAvailability
from app.schemas.recommendations import (
    RecommendationAction,
    RecommendationDataStatus,
    RecommendationEffort,
)
OPEN_BLOCKERS_RED_THRESHOLD = metric_threshold_value(
    "release.open_blockers", "critical"
)
HIGH_SEVERITY_BUGS_YELLOW_THRESHOLD = metric_threshold_value(
    "release.open_high_severity_bugs", "watch"
)
SCOPE_CHURN_YELLOW_THRESHOLD = (
    metric_threshold_value("release.scope_churn_7d_pct", "watch") / 100.0
)
REOPEN_RATE_YELLOW_THRESHOLD = (
    metric_threshold_value("release.reopen_rate_pct", "watch") / 100.0
)
CYCLE_TIME_YELLOW_THRESHOLD_DAYS = metric_threshold_value(
    "release.median_cycle_time_days", "watch"
)
WORKLOAD_CONCENTRATION_WATCH_MIN_PCT = metric_threshold_value(
    "sprint.workload_concentration_pct", "watch"
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
            title="Reduce reopen events",
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

    @staticmethod
    def build_release_recommendations(
        snapshot: Any,
        metric_availability: MetricAvailability | None = None,
    ) -> list[RecommendationAction]:
        candidates: list[_RecommendationRule] = []
        if RecommendationEngine._release_metric_available(metric_availability, "open_blockers") and snapshot.open_blockers > OPEN_BLOCKERS_RED_THRESHOLD:
            candidates.append(RecommendationEngine.RELEASE_RULES["open_blockers"])
        if (
            RecommendationEngine._release_metric_available(metric_availability, "open_high_severity_bugs")
            and snapshot.open_high_severity_bugs > HIGH_SEVERITY_BUGS_YELLOW_THRESHOLD
        ):
            candidates.append(RecommendationEngine.RELEASE_RULES["open_high_severity_bugs"])
        if (
            RecommendationEngine._release_metric_available(metric_availability, "scope_churn_7d_pct")
            and snapshot.scope_churn_7d_pct is not None
            and snapshot.scope_churn_7d_pct > SCOPE_CHURN_YELLOW_THRESHOLD * 100
        ):
            candidates.append(RecommendationEngine.RELEASE_RULES["scope_churn_7d_pct"])
        if (
            RecommendationEngine._release_metric_available(metric_availability, "reopen_rate_pct")
            and snapshot.reopen_rate_pct is not None
            and snapshot.reopen_rate_pct > REOPEN_RATE_YELLOW_THRESHOLD * 100
        ):
            candidates.append(RecommendationEngine.RELEASE_RULES["reopen_rate_pct"])
        if (
            RecommendationEngine._release_metric_available(metric_availability, "median_cycle_time_days")
            and
            snapshot.median_cycle_time_days is not None
            and snapshot.median_cycle_time_days > CYCLE_TIME_YELLOW_THRESHOLD_DAYS
        ):
            candidates.append(RecommendationEngine.RELEASE_RULES["median_cycle_time_days"])
        return RecommendationEngine._prioritize(candidates, RecommendationEngine.RELEASE_ORDER)

    @staticmethod
    def _release_metric_available(metric_availability: MetricAvailability | None, metric_name: str) -> bool:
        if metric_availability is None:
            return True
        item = metric_availability.metrics.get(metric_name)
        return item.available if item is not None else False

    @staticmethod
    def build_sprint_recommendations(
        snapshot: Any,
        sprint_issues: list[Any] | None = None,
        include_story_point_rules: bool = True,
    ) -> list[RecommendationAction]:
        # Retained as a compatibility argument; authoritative workload evidence
        # comes only from the persisted snapshot fields.
        _ = sprint_issues
        candidates: list[_RecommendationRule] = []
        evidence_by_key: dict[
            str,
            tuple[RecommendationDataStatus, list[str]],
        ] = {}
        components = (snapshot.delivery_confidence_components or {}) if include_story_point_rules else {}
        inputs = (snapshot.delivery_confidence_inputs or {}) if include_story_point_rules else {}

        if include_story_point_rules and (
            int(inputs.get("scope_change_count") or 0) > 0 or float(components.get("scope_stability", 100.0)) < 100.0
        ):
            candidates.append(RecommendationEngine.SPRINT_RULES["scope_stability"])
        if snapshot.open_blockers > OPEN_BLOCKERS_RED_THRESHOLD:
            candidates.append(RecommendationEngine.SPRINT_RULES["open_blockers"])
        if include_story_point_rules and (
            (
                snapshot.completed_scope_pct is not None
                and snapshot.completed_scope_pct < 100.0
            )
            or float(inputs.get("remaining_effective_points") or 0.0) > 0.0
            or float(components.get("progress_alignment", 100.0)) < 100.0
        ):
            candidates.append(RecommendationEngine.SPRINT_RULES["progress_alignment"])
        if snapshot.open_high_severity_bugs > HIGH_SEVERITY_BUGS_YELLOW_THRESHOLD:
            candidates.append(RecommendationEngine.SPRINT_RULES["open_high_severity_bugs"])
        workload_status = getattr(snapshot, "workload_distribution_status", None)
        workload_pct = getattr(snapshot, "workload_concentration_pct", None)
        if (
            workload_status in {"COMPUTED", "PARTIAL"}
            and workload_pct is not None
            and float(workload_pct) >= WORKLOAD_CONCENTRATION_WATCH_MIN_PCT
        ):
            candidates.append(RecommendationEngine.SPRINT_RULES["workload_concentration"])
            evidence_by_key["workload_concentration"] = (
                cast(RecommendationDataStatus, workload_status),
                list(getattr(snapshot, "workload_distribution_explanations", None) or []),
            )
        if (
            snapshot.median_cycle_time_days is not None
            and snapshot.median_cycle_time_days > CYCLE_TIME_YELLOW_THRESHOLD_DAYS
        ):
            candidates.append(RecommendationEngine.SPRINT_RULES["median_cycle_time_days"])
        if (
            snapshot.reopen_rate_pct is not None
            and snapshot.reopen_rate_pct > REOPEN_RATE_YELLOW_THRESHOLD * 100
        ):
            candidates.append(RecommendationEngine.SPRINT_RULES["reopen_rate_pct"])
        return RecommendationEngine._prioritize(
            candidates,
            RecommendationEngine.SPRINT_ORDER,
            evidence_by_key=evidence_by_key,
        )

    @staticmethod
    def _prioritize(
        candidates: list[_RecommendationRule],
        rule_order: list[str],
        evidence_by_key: dict[
            str,
            tuple[RecommendationDataStatus, list[str]],
        ]
        | None = None,
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
                dataStatus=(evidence_by_key or {}).get(item.key, ("COMPUTED", []))[0],
                explanations=(evidence_by_key or {}).get(item.key, ("COMPUTED", []))[1],
            )
            for index, item in enumerate(ordered)
        ]


