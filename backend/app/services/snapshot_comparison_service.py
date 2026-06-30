from collections.abc import Callable
from dataclasses import dataclass

from app.models import MetricSnapshot, SprintMetricSnapshot
from app.schemas.deltas import SnapshotDeltaComparison, SnapshotDeltaContributor
from app.services.analytics_service import DELIVERY_CONFIDENCE_WEIGHTS
from app.services.signal_service import SignalService


@dataclass(frozen=True)
class MetricDeltaRule:
    metric: str
    current_value: Callable[[object], int | float | None]
    previous_value: Callable[[object], int | float | None]
    impact: Callable[[object, object], float]


class SnapshotComparisonService:
    """Compare deterministic metric snapshots and explain confidence movement."""

    @staticmethod
    def compare_release_snapshots(
        current_snapshot: MetricSnapshot,
        previous_snapshot: MetricSnapshot,
    ) -> SnapshotDeltaComparison:
        current_confidence = SignalService._confidence_score_for_snapshot(current_snapshot)
        previous_confidence = SignalService._confidence_score_for_snapshot(previous_snapshot)
        rules = [
            MetricDeltaRule(
                metric="open_blockers",
                current_value=lambda snapshot: snapshot.open_blockers,
                previous_value=lambda snapshot: snapshot.open_blockers,
                impact=lambda current, previous: SnapshotComparisonService._release_risk_impact(
                    current=current,
                    previous=previous,
                    metric="open_blockers",
                ),
            ),
            MetricDeltaRule(
                metric="open_high_severity_bugs",
                current_value=lambda snapshot: snapshot.open_high_severity_bugs,
                previous_value=lambda snapshot: snapshot.open_high_severity_bugs,
                impact=lambda current, previous: SnapshotComparisonService._release_risk_impact(
                    current=current,
                    previous=previous,
                    metric="open_high_severity_bugs",
                ),
            ),
            MetricDeltaRule(
                metric="reopen_rate_pct",
                current_value=lambda snapshot: snapshot.reopen_rate_pct,
                previous_value=lambda snapshot: snapshot.reopen_rate_pct,
                impact=lambda current, previous: SnapshotComparisonService._release_risk_impact(
                    current=current,
                    previous=previous,
                    metric="reopen_rate_pct",
                ),
            ),
            MetricDeltaRule(
                metric="median_cycle_time_days",
                current_value=lambda snapshot: snapshot.median_cycle_time_days,
                previous_value=lambda snapshot: snapshot.median_cycle_time_days,
                impact=lambda current, previous: SnapshotComparisonService._release_risk_impact(
                    current=current,
                    previous=previous,
                    metric="median_cycle_time_days",
                ),
            ),
            MetricDeltaRule(
                metric="scope_churn_7d_pct",
                current_value=lambda snapshot: snapshot.scope_churn_7d_pct,
                previous_value=lambda snapshot: snapshot.scope_churn_7d_pct,
                impact=lambda current, previous: SnapshotComparisonService._release_risk_impact(
                    current=current,
                    previous=previous,
                    metric="scope_churn_7d_pct",
                ),
            ),
            MetricDeltaRule(
                metric="completed_tickets",
                current_value=lambda snapshot: snapshot.completed_tickets,
                previous_value=lambda snapshot: snapshot.completed_tickets,
                impact=lambda _current, _previous: 0.0,
            ),
        ]
        return SnapshotDeltaComparison(
            confidence_delta=SnapshotComparisonService._rounded_delta(current_confidence, previous_confidence) or 0.0,
            contributors=SnapshotComparisonService._build_contributors(
                current_snapshot=current_snapshot,
                previous_snapshot=previous_snapshot,
                rules=rules,
            ),
        )

    @staticmethod
    def compare_sprint_snapshots(
        current_snapshot: SprintMetricSnapshot,
        previous_snapshot: SprintMetricSnapshot,
    ) -> SnapshotDeltaComparison:
        current_confidence = current_snapshot.delivery_confidence_score
        previous_confidence = previous_snapshot.delivery_confidence_score
        rules = [
            SnapshotComparisonService._sprint_component_rule("velocity_fit", "velocity_fit"),
            SnapshotComparisonService._sprint_component_rule("scope_stability", "scope_stability"),
            SnapshotComparisonService._sprint_component_rule("progress_alignment", "progress_alignment"),
            SnapshotComparisonService._sprint_component_rule("blocker_health", "blocker_penalty"),
            MetricDeltaRule(
                metric="reopen_rate_pct",
                current_value=lambda snapshot: snapshot.reopen_rate_pct,
                previous_value=lambda snapshot: snapshot.reopen_rate_pct,
                impact=lambda _current, _previous: 0.0,
            ),
            MetricDeltaRule(
                metric="bugs_created_during_sprint",
                current_value=lambda snapshot: snapshot.bugs_created_during_sprint,
                previous_value=lambda snapshot: snapshot.bugs_created_during_sprint,
                impact=lambda _current, _previous: 0.0,
            ),
        ]
        return SnapshotDeltaComparison(
            confidence_delta=SnapshotComparisonService._rounded_delta(current_confidence, previous_confidence),
            contributors=SnapshotComparisonService._build_contributors(
                current_snapshot=current_snapshot,
                previous_snapshot=previous_snapshot,
                rules=rules,
            ),
        )

    @staticmethod
    def primary_driver(comparison: SnapshotDeltaComparison) -> str:
        scored = [item for item in comparison.contributors if item.impact != 0]
        if scored:
            return max(scored, key=lambda item: (abs(item.impact), abs(item.delta), item.metric)).metric
        if comparison.contributors:
            return max(comparison.contributors, key=lambda item: (abs(item.delta), item.metric)).metric
        return "No material change"

    @staticmethod
    def _sprint_component_rule(metric: str, component_key: str) -> MetricDeltaRule:
        return MetricDeltaRule(
            metric=metric,
            current_value=lambda snapshot: SnapshotComparisonService._sprint_component_value(snapshot, component_key),
            previous_value=lambda snapshot: SnapshotComparisonService._sprint_component_value(snapshot, component_key),
            impact=lambda current, previous: SnapshotComparisonService._sprint_component_impact(
                current=current,
                previous=previous,
                component_key=component_key,
            ),
        )

    @staticmethod
    def _build_contributors(
        current_snapshot: object,
        previous_snapshot: object,
        rules: list[MetricDeltaRule],
    ) -> list[SnapshotDeltaContributor]:
        contributors: list[SnapshotDeltaContributor] = []
        for rule in rules:
            delta = SnapshotComparisonService._rounded_delta(
                rule.current_value(current_snapshot),
                rule.previous_value(previous_snapshot),
            )
            if delta is None or delta == 0:
                continue

            contributors.append(
                SnapshotDeltaContributor(
                    metric=rule.metric,
                    delta=delta,
                    impact=round(rule.impact(current_snapshot, previous_snapshot), 2),
                    direction="up" if delta > 0 else "down",
                )
            )

        return sorted(
            contributors,
            key=lambda item: (abs(item.impact), abs(item.delta), item.metric),
            reverse=True,
        )

    @staticmethod
    def _rounded_delta(current_value: int | float | None, previous_value: int | float | None) -> float | None:
        if current_value is None or previous_value is None:
            return None
        return round(float(current_value) - float(previous_value), 2)

    @staticmethod
    def _release_risk_impact(current: MetricSnapshot, previous: MetricSnapshot, metric: str) -> float:
        current_points = SignalService._compute_release_risk_points(
            open_blockers=current.open_blockers,
            open_high_severity_bugs=current.open_high_severity_bugs,
            scope_churn_7d_pct=current.scope_churn_7d_pct,
            reopen_rate_pct=current.reopen_rate_pct,
            median_cycle_time_days=current.median_cycle_time_days,
        )
        previous_points = SignalService._compute_release_risk_points(
            open_blockers=previous.open_blockers,
            open_high_severity_bugs=previous.open_high_severity_bugs,
            scope_churn_7d_pct=previous.scope_churn_7d_pct,
            reopen_rate_pct=previous.reopen_rate_pct,
            median_cycle_time_days=previous.median_cycle_time_days,
        )
        return round(previous_points.get(metric, 0.0) - current_points.get(metric, 0.0), 2)

    @staticmethod
    def _sprint_component_value(snapshot: SprintMetricSnapshot, component_key: str) -> float | None:
        if snapshot.delivery_confidence_components is None:
            return None
        value = snapshot.delivery_confidence_components.get(component_key)
        return float(value) if value is not None else None

    @staticmethod
    def _sprint_component_impact(
        current: SprintMetricSnapshot,
        previous: SprintMetricSnapshot,
        component_key: str,
    ) -> float:
        current_value = SnapshotComparisonService._sprint_component_value(current, component_key)
        previous_value = SnapshotComparisonService._sprint_component_value(previous, component_key)
        delta = SnapshotComparisonService._rounded_delta(current_value, previous_value)
        if delta is None:
            return 0.0
        return round(delta * DELIVERY_CONFIDENCE_WEIGHTS[component_key], 2)
