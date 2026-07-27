"""Immutable metadata for the release and sprint metrics exposed by the API.

PRODUCT_RULES.md is the normative product authority.  This module is the
machine-readable inventory of that approved metadata; it deliberately does not
calculate metrics, evaluate signals, or determine runtime availability.
"""

import math
from dataclasses import dataclass
from types import MappingProxyType
from typing import Literal

from app.utils.constants import RULESET_VERSION

MetricScope = Literal["release", "sprint"]
MetricCategory = Literal["delivery", "quality", "flow", "risk", "snapshot"]
MetricUnit = Literal["tickets", "percent", "days", "score", "gates"]
MetricFormat = Literal["integer", "decimal_1", "decimal_2", "decimal_4", "percent_2"]
MetricSeverity = Literal["watch", "critical"]
MetricComparison = Literal["gt", "gte", "lt", "lte"]
MetricApiLocation = Literal["metric_values", "response_field", "chart_only"]
PartialValuePolicy = Literal[
    "confirmed_minimum",
    "calculated_from_available_data",
    "unavailable",
    "not_supported",
]

CATALOG_VERSION = 2


@dataclass(frozen=True, slots=True)
class MetricThreshold:
    """One approved threshold boundary, ordered most severe first."""

    severity: MetricSeverity
    comparison: MetricComparison
    value: int | float
    meaning: str


@dataclass(frozen=True, slots=True)
class MetricAvailabilityMetadata:
    """Static dependencies and evidence locations for one metric."""

    dependencies: tuple[str, ...]
    partial_value_policy: PartialValuePolicy
    supports_not_applicable: bool
    evidence_fields: tuple[str, ...]
    minimum_coverage_pct: float | None = None


@dataclass(frozen=True, slots=True)
class MetricDefinition:
    """Mechanical metadata for a metric that is part of the public API."""

    key: str
    scope: MetricScope
    api_field: str
    label: str
    description: str
    category: MetricCategory
    unit: MetricUnit
    formatting: MetricFormat
    display_order: int
    thresholds: tuple[MetricThreshold, ...]
    severity_meaning: str
    availability: MetricAvailabilityMetadata
    historical_series: bool
    signal_participation: bool
    confidence_participation: bool
    chart_participation: bool
    report_participation: bool
    ruleset_version: int
    api_location: MetricApiLocation = "metric_values"


def _availability(
    *dependencies: str,
    partial_value_policy: PartialValuePolicy,
    supports_not_applicable: bool = False,
    evidence_fields: tuple[str, ...],
    minimum_coverage_pct: float | None = None,
) -> MetricAvailabilityMetadata:
    return MetricAvailabilityMetadata(
        dependencies=dependencies,
        partial_value_policy=partial_value_policy,
        supports_not_applicable=supports_not_applicable,
        evidence_fields=evidence_fields,
        minimum_coverage_pct=minimum_coverage_pct,
    )


NO_APPROVED_SEVERITY = "No product-rule severity classification applies to this metric."
NO_BREACH_IS_HEALTHY = (
    "No matching threshold is healthy; the most severe matching threshold wins."
)

RELEASE_METRICS: tuple[MetricDefinition, ...] = (
    MetricDefinition(
        key="release.open_blockers",
        scope="release",
        api_field="open_blockers",
        label="Open blockers",
        description="Current release tickets classified as blockers that are not done.",
        category="risk",
        unit="tickets",
        formatting="integer",
        display_order=1,
        thresholds=(
            MetricThreshold(
                severity="critical",
                comparison="gt",
                value=0,
                meaning="Any open blocker is a hard RED release condition.",
            ),
        ),
        severity_meaning=NO_BREACH_IS_HEALTHY,
        availability=_availability(
            "ticket_count",
            "release_assignment",
            partial_value_policy="confirmed_minimum",
            evidence_fields=(
                "metric_issue_keys.open_blockers",
                "calculation_provenance.metric_evidence.open_blockers",
            ),
        ),
        historical_series=True,
        signal_participation=True,
        confidence_participation=True,
        chart_participation=True,
        report_participation=True,
        ruleset_version=RULESET_VERSION,
    ),
    MetricDefinition(
        key="release.open_high_severity_bugs",
        scope="release",
        api_field="open_high_severity_bugs",
        label="Open high-severity bugs",
        description="Current release bugs with configured high severity that are not done.",
        category="quality",
        unit="tickets",
        formatting="integer",
        display_order=2,
        thresholds=(
            MetricThreshold(
                severity="critical",
                comparison="gt",
                value=1,
                meaning="More than one open high-severity bug is a hard RED release condition.",
            ),
            MetricThreshold(
                severity="watch",
                comparison="gt",
                value=0,
                meaning="One open high-severity bug is a hard YELLOW release condition.",
            ),
        ),
        severity_meaning=NO_BREACH_IS_HEALTHY,
        availability=_availability(
            "ticket_count",
            "release_assignment",
            partial_value_policy="confirmed_minimum",
            evidence_fields=(
                "metric_issue_keys.open_high_severity_bugs",
                "calculation_provenance.metric_evidence.open_high_severity_bugs",
            ),
        ),
        historical_series=True,
        signal_participation=True,
        confidence_participation=True,
        chart_participation=True,
        report_participation=True,
        ruleset_version=RULESET_VERSION,
    ),
    MetricDefinition(
        key="release.scope_completed_pct",
        scope="release",
        api_field="scope_completed_pct",
        label="Scope completed",
        description="Percentage of current release tickets whose status is done.",
        category="delivery",
        unit="percent",
        formatting="percent_2",
        display_order=3,
        thresholds=(),
        severity_meaning=NO_APPROVED_SEVERITY,
        availability=_availability(
            "ticket_count",
            "release_assignment",
            partial_value_policy="unavailable",
            evidence_fields=(
                "calculation_provenance.metric_evidence.scope_completed_pct",
            ),
        ),
        historical_series=True,
        signal_participation=False,
        confidence_participation=False,
        chart_participation=True,
        report_participation=True,
        ruleset_version=RULESET_VERSION,
    ),
    MetricDefinition(
        key="release.completed_tickets",
        scope="release",
        api_field="completed_tickets",
        label="Completed tickets",
        description="Current release tickets whose status is done.",
        category="delivery",
        unit="tickets",
        formatting="integer",
        display_order=4,
        thresholds=(),
        severity_meaning=NO_APPROVED_SEVERITY,
        availability=_availability(
            "ticket_count",
            "release_assignment",
            partial_value_policy="confirmed_minimum",
            evidence_fields=(
                "metric_issue_keys.completed_tickets",
                "calculation_provenance.metric_evidence.completed_tickets",
            ),
        ),
        historical_series=True,
        signal_participation=False,
        confidence_participation=False,
        chart_participation=True,
        report_participation=True,
        ruleset_version=RULESET_VERSION,
    ),
    MetricDefinition(
        key="release.scope_churn_7d_pct",
        scope="release",
        api_field="scope_churn_7d_pct",
        label="Scope churn 7d",
        description="Distinct release membership changes per 100 observed-scope tickets in the inclusive seven-day window.",
        category="risk",
        unit="percent",
        formatting="percent_2",
        display_order=5,
        thresholds=(
            MetricThreshold(
                severity="critical",
                comparison="gt",
                value=20.0,
                meaning="Scope churn above 20% is a hard RED release condition.",
            ),
            MetricThreshold(
                severity="watch",
                comparison="gt",
                value=10.0,
                meaning="Scope churn above 10% is a hard YELLOW release condition.",
            ),
        ),
        severity_meaning=NO_BREACH_IS_HEALTHY,
        availability=_availability(
            "ticket_count",
            "history_changelog",
            "release_assignment",
            partial_value_policy="unavailable",
            evidence_fields=(
                "calculation_provenance.metric_evidence.scope_churn_7d_pct",
            ),
        ),
        historical_series=True,
        signal_participation=True,
        confidence_participation=True,
        chart_participation=True,
        report_participation=True,
        ruleset_version=RULESET_VERSION,
    ),
    MetricDefinition(
        key="release.scope_added_7d_count",
        scope="release",
        api_field="scope_added_7d_count",
        label="Scope added 7d",
        description="Distinct tickets added to the release in the inclusive seven-day window.",
        category="snapshot",
        unit="tickets",
        formatting="integer",
        display_order=6,
        thresholds=(),
        severity_meaning=NO_APPROVED_SEVERITY,
        availability=_availability(
            "ticket_count",
            "history_changelog",
            "release_assignment",
            partial_value_policy="confirmed_minimum",
            evidence_fields=(
                "calculation_provenance.issue_key_evidence.scope_added_7d",
                "calculation_provenance.metric_evidence.scope_added_7d_count",
            ),
        ),
        historical_series=True,
        signal_participation=False,
        confidence_participation=False,
        chart_participation=True,
        report_participation=True,
        ruleset_version=RULESET_VERSION,
    ),
    MetricDefinition(
        key="release.scope_removed_7d_count",
        scope="release",
        api_field="scope_removed_7d_count",
        label="Scope removed 7d",
        description="Distinct tickets removed from the release in the inclusive seven-day window.",
        category="snapshot",
        unit="tickets",
        formatting="integer",
        display_order=7,
        thresholds=(),
        severity_meaning=NO_APPROVED_SEVERITY,
        availability=_availability(
            "ticket_count",
            "history_changelog",
            "release_assignment",
            partial_value_policy="confirmed_minimum",
            evidence_fields=(
                "calculation_provenance.issue_key_evidence.scope_removed_7d",
                "calculation_provenance.metric_evidence.scope_removed_7d_count",
            ),
        ),
        historical_series=True,
        signal_participation=False,
        confidence_participation=False,
        chart_participation=True,
        report_participation=True,
        ruleset_version=RULESET_VERSION,
    ),
    MetricDefinition(
        key="release.median_cycle_time_days",
        scope="release",
        api_field="median_cycle_time_days",
        label="Median cycle time",
        description="Median days from the first valid in-progress transition to the first later done transition.",
        category="flow",
        unit="days",
        formatting="decimal_4",
        display_order=8,
        thresholds=(
            MetricThreshold(
                severity="watch",
                comparison="gt",
                value=7.0,
                meaning="Median cycle time above seven days is a hard YELLOW release condition.",
            ),
        ),
        severity_meaning=NO_BREACH_IS_HEALTHY,
        availability=_availability(
            "ticket_count",
            "completed_tickets",
            "history_changelog",
            "release_assignment",
            partial_value_policy="unavailable",
            evidence_fields=(
                "calculation_provenance.metric_evidence.median_cycle_time_days",
            ),
        ),
        historical_series=True,
        signal_participation=True,
        confidence_participation=True,
        chart_participation=True,
        report_participation=True,
        ruleset_version=RULESET_VERSION,
    ),
    MetricDefinition(
        key="release.reopen_rate_pct",
        scope="release",
        api_field="reopen_rate_pct",
        label="Reopen events per 100 eligible tickets",
        description="Distinct done-to-not-done transitions per 100 eligible release tickets.",
        category="quality",
        unit="percent",
        formatting="percent_2",
        display_order=9,
        thresholds=(
            MetricThreshold(
                severity="critical",
                comparison="gt",
                value=15.0,
                meaning="A reopen event rate above 15 is a hard RED release condition.",
            ),
            MetricThreshold(
                severity="watch",
                comparison="gt",
                value=10.0,
                meaning="A reopen event rate above 10 is a hard YELLOW release condition.",
            ),
        ),
        severity_meaning=NO_BREACH_IS_HEALTHY,
        availability=_availability(
            "ticket_count",
            "history_changelog",
            "release_assignment",
            partial_value_policy="unavailable",
            evidence_fields=("calculation_provenance.metric_evidence.reopen_rate_pct",),
        ),
        historical_series=True,
        signal_participation=True,
        confidence_participation=True,
        chart_participation=True,
        report_participation=True,
        ruleset_version=RULESET_VERSION,
    ),
    MetricDefinition(
        key="release.confidence_score",
        scope="release",
        api_field="confidence_score",
        label="Release confidence",
        description="Release confidence after subtracting approved weighted risk points from 100.",
        category="risk",
        unit="score",
        formatting="decimal_1",
        display_order=10,
        thresholds=(
            MetricThreshold(
                severity="critical",
                comparison="lte",
                value=60.0,
                meaning="A release confidence score at or below 60 is RED.",
            ),
            MetricThreshold(
                severity="watch",
                comparison="lte",
                value=90.0,
                meaning="A release confidence score above 60 and at or below 90 is YELLOW.",
            ),
        ),
        severity_meaning="Scores above 90 are GREEN; the most severe matching threshold wins.",
        availability=_availability(
            "ticket_count",
            "release_assignment",
            partial_value_policy="unavailable",
            evidence_fields=(
                "calculation_provenance.component_inputs",
                "calculation_provenance.component_outputs.risk_points",
                "calculation_provenance.component_outputs.confidence_breakdown",
            ),
        ),
        historical_series=True,
        signal_participation=True,
        confidence_participation=True,
        chart_participation=True,
        report_participation=True,
        ruleset_version=RULESET_VERSION,
        api_location="response_field",
    ),
    MetricDefinition(
        key="release.gates_passed_count",
        scope="release",
        api_field="gates_passed_count",
        label="Gates passed",
        description="Number of the five approved release-readiness gates that pass.",
        category="delivery",
        unit="gates",
        formatting="integer",
        display_order=11,
        thresholds=(),
        severity_meaning=NO_APPROVED_SEVERITY,
        availability=_availability(
            "ticket_count",
            "release_assignment",
            partial_value_policy="unavailable",
            evidence_fields=("calculation_provenance.component_outputs.release_gates",),
        ),
        historical_series=True,
        signal_participation=False,
        confidence_participation=False,
        chart_participation=True,
        report_participation=True,
        ruleset_version=RULESET_VERSION,
        api_location="chart_only",
    ),
    MetricDefinition(
        key="release.readiness_pct",
        scope="release",
        api_field="readiness_pct",
        label="Readiness",
        description="Percentage of the five approved release-readiness gates that pass.",
        category="delivery",
        unit="percent",
        formatting="percent_2",
        display_order=12,
        thresholds=(),
        severity_meaning=NO_APPROVED_SEVERITY,
        availability=_availability(
            "ticket_count",
            "release_assignment",
            partial_value_policy="unavailable",
            evidence_fields=(
                "calculation_provenance.component_outputs.release_gates",
                "calculation_provenance.component_outputs.readiness_pct",
            ),
        ),
        historical_series=True,
        signal_participation=False,
        confidence_participation=False,
        chart_participation=True,
        report_participation=True,
        ruleset_version=RULESET_VERSION,
        api_location="chart_only",
    ),
)


SPRINT_METRICS: tuple[MetricDefinition, ...] = (
    MetricDefinition(
        key="sprint.committed_scope",
        scope="sprint",
        api_field="committed_scope",
        label="Current sprint scope",
        description="Distinct tickets currently assigned to the sprint at snapshot time.",
        category="delivery",
        unit="tickets",
        formatting="integer",
        display_order=1,
        thresholds=(),
        severity_meaning=NO_APPROVED_SEVERITY,
        availability=_availability(
            "ticket_count",
            "sprint_assignment",
            partial_value_policy="not_supported",
            evidence_fields=("calculation_provenance.metric_evidence.committed_scope",),
        ),
        historical_series=False,
        signal_participation=False,
        confidence_participation=True,
        chart_participation=False,
        report_participation=True,
        ruleset_version=RULESET_VERSION,
    ),
    MetricDefinition(
        key="sprint.completed_scope_pct",
        scope="sprint",
        api_field="completed_scope_pct",
        label="Completed scope",
        description="Percentage of current sprint tickets whose status is done.",
        category="delivery",
        unit="percent",
        formatting="percent_2",
        display_order=2,
        thresholds=(),
        severity_meaning=NO_APPROVED_SEVERITY,
        availability=_availability(
            "ticket_count",
            "ticket_status",
            "sprint_assignment",
            partial_value_policy="unavailable",
            evidence_fields=(
                "calculation_provenance.metric_evidence.completed_scope_pct",
            ),
        ),
        historical_series=False,
        signal_participation=False,
        confidence_participation=False,
        chart_participation=True,
        report_participation=True,
        ruleset_version=RULESET_VERSION,
    ),
    MetricDefinition(
        key="sprint.scope_creep_pct",
        scope="sprint",
        api_field="scope_creep_pct",
        label="Scope creep",
        description="Post-start sprint addition and removal events per 100 initial-commitment tickets.",
        category="delivery",
        unit="percent",
        formatting="percent_2",
        display_order=3,
        thresholds=(
            MetricThreshold(
                severity="critical",
                comparison="gt",
                value=20.0,
                meaning="Scope creep above 20% is critical.",
            ),
            MetricThreshold(
                severity="watch",
                comparison="gt",
                value=10.0,
                meaning="Scope creep above 10% through 20% is watch.",
            ),
        ),
        severity_meaning="Values at or below 10% are healthy; the most severe matching threshold wins.",
        availability=_availability(
            "sprint_duration",
            "project_changelog_completeness",
            "sprint_assignment",
            partial_value_policy="unavailable",
            evidence_fields=(
                "scope_movement.evidence",
                "calculation_provenance.metric_evidence.scope_creep_pct",
            ),
        ),
        historical_series=True,
        signal_participation=False,
        confidence_participation=True,
        chart_participation=True,
        report_participation=True,
        ruleset_version=RULESET_VERSION,
    ),
    MetricDefinition(
        key="sprint.open_blockers",
        scope="sprint",
        api_field="open_blockers",
        label="Open blockers",
        description="Current sprint tickets classified as blockers that are not done.",
        category="risk",
        unit="tickets",
        formatting="integer",
        display_order=4,
        thresholds=(),
        severity_meaning=NO_APPROVED_SEVERITY,
        availability=_availability(
            "ticket_count",
            "sprint_assignment",
            partial_value_policy="confirmed_minimum",
            evidence_fields=(
                "metric_issue_keys.open_blockers",
                "calculation_provenance.metric_evidence.open_blockers",
            ),
        ),
        historical_series=False,
        signal_participation=False,
        confidence_participation=True,
        chart_participation=True,
        report_participation=True,
        ruleset_version=RULESET_VERSION,
    ),
    MetricDefinition(
        key="sprint.open_high_severity_bugs",
        scope="sprint",
        api_field="open_high_severity_bugs",
        label="Open high-severity bugs",
        description="Current sprint bugs with configured high severity that are not done.",
        category="quality",
        unit="tickets",
        formatting="integer",
        display_order=5,
        thresholds=(),
        severity_meaning=NO_APPROVED_SEVERITY,
        availability=_availability(
            "ticket_count",
            "sprint_assignment",
            partial_value_policy="confirmed_minimum",
            evidence_fields=(
                "metric_issue_keys.open_high_severity_bugs",
                "calculation_provenance.metric_evidence.open_high_severity_bugs",
            ),
        ),
        historical_series=False,
        signal_participation=False,
        confidence_participation=False,
        chart_participation=True,
        report_participation=True,
        ruleset_version=RULESET_VERSION,
    ),
    MetricDefinition(
        key="sprint.bugs_created_during_sprint",
        scope="sprint",
        api_field="bugs_created_during_sprint",
        label="Bugs created during sprint",
        description="Sprint bugs created within the approved inclusive sprint time window.",
        category="quality",
        unit="tickets",
        formatting="integer",
        display_order=6,
        thresholds=(),
        severity_meaning=NO_APPROVED_SEVERITY,
        availability=_availability(
            "ticket_count",
            "sprint_assignment",
            partial_value_policy="confirmed_minimum",
            evidence_fields=(
                "metric_issue_keys.bugs_created_during_sprint",
                "metric_issue_keys.bugs_created_during_sprint_missing_created_at",
                "calculation_provenance.metric_evidence.bugs_created_during_sprint",
            ),
        ),
        historical_series=False,
        signal_participation=False,
        confidence_participation=False,
        chart_participation=True,
        report_participation=True,
        ruleset_version=RULESET_VERSION,
    ),
    MetricDefinition(
        key="sprint.in_progress_count",
        scope="sprint",
        api_field="in_progress_count",
        label="In progress",
        description="Current sprint tickets in a configured in-progress status.",
        category="snapshot",
        unit="tickets",
        formatting="integer",
        display_order=7,
        thresholds=(),
        severity_meaning=NO_APPROVED_SEVERITY,
        availability=_availability(
            "ticket_count",
            "ticket_status",
            "sprint_assignment",
            partial_value_policy="confirmed_minimum",
            evidence_fields=(
                "calculation_provenance.metric_evidence.in_progress_count",
            ),
        ),
        historical_series=False,
        signal_participation=False,
        confidence_participation=False,
        chart_participation=False,
        report_participation=True,
        ruleset_version=RULESET_VERSION,
    ),
    MetricDefinition(
        key="sprint.not_started_count",
        scope="sprint",
        api_field="not_started_count",
        label="Not started",
        description="Known-status sprint tickets in neither done nor configured in-progress states.",
        category="snapshot",
        unit="tickets",
        formatting="integer",
        display_order=8,
        thresholds=(),
        severity_meaning=NO_APPROVED_SEVERITY,
        availability=_availability(
            "ticket_count",
            "ticket_status",
            "sprint_assignment",
            partial_value_policy="confirmed_minimum",
            evidence_fields=(
                "calculation_provenance.metric_evidence.not_started_count",
            ),
        ),
        historical_series=False,
        signal_participation=False,
        confidence_participation=False,
        chart_participation=False,
        report_participation=True,
        ruleset_version=RULESET_VERSION,
    ),
    MetricDefinition(
        key="sprint.rollover_count",
        scope="sprint",
        api_field="rollover_count",
        label="Unfinished closed-sprint scope",
        description="Current non-done tickets in a closed sprint; it does not prove movement to another sprint.",
        category="delivery",
        unit="tickets",
        formatting="integer",
        display_order=9,
        thresholds=(),
        severity_meaning=NO_APPROVED_SEVERITY,
        availability=_availability(
            "ticket_count",
            "ticket_status",
            "sprint_assignment",
            partial_value_policy="confirmed_minimum",
            supports_not_applicable=True,
            evidence_fields=("calculation_provenance.metric_evidence.rollover_count",),
        ),
        historical_series=False,
        signal_participation=False,
        confidence_participation=False,
        chart_participation=True,
        report_participation=True,
        ruleset_version=RULESET_VERSION,
    ),
    MetricDefinition(
        key="sprint.median_cycle_time_days",
        scope="sprint",
        api_field="median_cycle_time_days",
        label="Median cycle time",
        description="Median days from the first valid in-progress transition to the first later done transition.",
        category="flow",
        unit="days",
        formatting="decimal_4",
        display_order=10,
        thresholds=(),
        severity_meaning=NO_APPROVED_SEVERITY,
        availability=_availability(
            "ticket_count",
            "completed_tickets",
            "history_changelog",
            "sprint_assignment",
            partial_value_policy="unavailable",
            evidence_fields=(
                "calculation_provenance.metric_evidence.median_cycle_time_days",
            ),
        ),
        historical_series=False,
        signal_participation=False,
        confidence_participation=False,
        chart_participation=True,
        report_participation=True,
        ruleset_version=RULESET_VERSION,
    ),
    MetricDefinition(
        key="sprint.reopen_rate_pct",
        scope="sprint",
        api_field="reopen_rate_pct",
        label="Reopen events per 100 eligible tickets",
        description="Distinct done-to-not-done transitions per 100 eligible sprint tickets.",
        category="quality",
        unit="percent",
        formatting="percent_2",
        display_order=11,
        thresholds=(),
        severity_meaning=NO_APPROVED_SEVERITY,
        availability=_availability(
            "ticket_count",
            "history_changelog",
            "sprint_assignment",
            partial_value_policy="unavailable",
            evidence_fields=("calculation_provenance.metric_evidence.reopen_rate_pct",),
        ),
        historical_series=False,
        signal_participation=False,
        confidence_participation=False,
        chart_participation=True,
        report_participation=True,
        ruleset_version=RULESET_VERSION,
    ),
    MetricDefinition(
        key="sprint.workload_concentration_pct",
        scope="sprint",
        api_field="workload_concentration_pct",
        label="Workload concentration",
        description="Share of included active sprint story points owned by the top assignee.",
        category="risk",
        unit="percent",
        formatting="percent_2",
        display_order=12,
        thresholds=(
            MetricThreshold(
                severity="critical",
                comparison="gt",
                value=50.0,
                meaning="Workload concentration above 50% is critical.",
            ),
            MetricThreshold(
                severity="watch",
                comparison="gte",
                value=35.0,
                meaning="Workload concentration from 35% through 50% is watch.",
            ),
        ),
        severity_meaning="Values below 35% are healthy; the most severe matching threshold wins.",
        availability=_availability(
            "ticket_count",
            "ticket_status",
            "story_points",
            "assignee_identity",
            "sprint_assignment",
            partial_value_policy="calculated_from_available_data",
            supports_not_applicable=True,
            minimum_coverage_pct=50.0,
            evidence_fields=(
                "workload_distribution.evidence",
                "calculation_provenance.metric_evidence.workload_concentration_pct",
            ),
        ),
        historical_series=False,
        signal_participation=False,
        confidence_participation=False,
        chart_participation=False,
        report_participation=True,
        ruleset_version=RULESET_VERSION,
    ),
    MetricDefinition(
        key="sprint.delivery_confidence_score",
        scope="sprint",
        api_field="delivery_confidence_score",
        label="Delivery confidence",
        description="Composite score from progress alignment, velocity fit, blocker health, and scope stability.",
        category="delivery",
        unit="score",
        formatting="decimal_2",
        display_order=13,
        thresholds=(),
        severity_meaning=NO_APPROVED_SEVERITY,
        availability=_availability(
            "ticket_count",
            "story_points",
            "ticket_status",
            "blocker_classification",
            "sprint_duration",
            "project_changelog_completeness",
            "sprint_assignment",
            partial_value_policy="calculated_from_available_data",
            minimum_coverage_pct=50.0,
            evidence_fields=(
                "story_point_coverage",
                "delivery_confidence",
                "calculation_provenance.delivery_confidence_prerequisites",
                "calculation_provenance.component_inputs",
                "calculation_provenance.component_outputs.components",
            ),
        ),
        historical_series=True,
        signal_participation=False,
        confidence_participation=True,
        chart_participation=True,
        report_participation=True,
        ruleset_version=RULESET_VERSION,
    ),
)


METRIC_CATALOG: tuple[MetricDefinition, ...] = RELEASE_METRICS + SPRINT_METRICS


def _validate_catalog() -> None:
    if CATALOG_VERSION < 1:
        raise RuntimeError("Metric catalog version must be positive.")

    keys: set[str] = set()
    fields_by_scope: dict[MetricScope, set[str]] = {"release": set(), "sprint": set()}
    severity_order = {"critical": 0, "watch": 1}

    for scope, definitions in (
        ("release", RELEASE_METRICS),
        ("sprint", SPRINT_METRICS),
    ):
        expected_orders = list(range(1, len(definitions) + 1))
        actual_orders = [definition.display_order for definition in definitions]
        if actual_orders != expected_orders:
            raise RuntimeError(
                f"{scope.title()} metric display order must be contiguous."
            )

        for definition in definitions:
            expected_key = f"{scope}.{definition.api_field}"
            if definition.scope != scope or definition.key != expected_key:
                raise RuntimeError(
                    f"Metric key '{definition.key}' does not match its scope and API field."
                )
            if definition.key in keys:
                raise RuntimeError(f"Duplicate metric key '{definition.key}'.")
            if definition.api_field in fields_by_scope[scope]:
                raise RuntimeError(
                    f"Duplicate {scope} API metric field '{definition.api_field}'."
                )
            if not all(
                (definition.label, definition.description, definition.severity_meaning)
            ):
                raise RuntimeError(
                    f"Metric '{definition.key}' has incomplete presentation metadata."
                )
            if not definition.availability.dependencies:
                raise RuntimeError(
                    f"Metric '{definition.key}' has no availability dependencies."
                )
            if not definition.availability.evidence_fields:
                raise RuntimeError(
                    f"Metric '{definition.key}' has no evidence metadata."
                )
            if definition.ruleset_version != RULESET_VERSION:
                raise RuntimeError(
                    f"Metric '{definition.key}' does not use the current ruleset version."
                )
            if (
                definition.api_location == "chart_only"
                and not definition.chart_participation
            ):
                raise RuntimeError(
                    f"Chart-only metric '{definition.key}' must participate in charts."
                )
            minimum_coverage_pct = definition.availability.minimum_coverage_pct
            if minimum_coverage_pct is not None and (
                not math.isfinite(minimum_coverage_pct)
                or not 0.0 <= minimum_coverage_pct <= 100.0
            ):
                raise RuntimeError(
                    f"Metric '{definition.key}' has invalid minimum coverage."
                )

            threshold_severities = [
                threshold.severity for threshold in definition.thresholds
            ]
            if len(threshold_severities) != len(set(threshold_severities)):
                raise RuntimeError(
                    f"Metric '{definition.key}' repeats a threshold severity."
                )
            if threshold_severities != sorted(
                threshold_severities, key=severity_order.__getitem__
            ):
                raise RuntimeError(
                    f"Metric '{definition.key}' thresholds must be most severe first."
                )
            if any(
                not math.isfinite(threshold.value)
                for threshold in definition.thresholds
            ):
                raise RuntimeError(
                    f"Metric '{definition.key}' has a non-finite threshold."
                )

            keys.add(definition.key)
            fields_by_scope[scope].add(definition.api_field)


_validate_catalog()

METRIC_CATALOG_BY_KEY = MappingProxyType(
    {metric.key: metric for metric in METRIC_CATALOG}
)


def metric_threshold(metric_key: str, severity: MetricSeverity) -> MetricThreshold:
    """Return one explicitly cataloged severity threshold."""

    definition = METRIC_CATALOG_BY_KEY[metric_key]
    try:
        return next(
            threshold
            for threshold in definition.thresholds
            if threshold.severity == severity
        )
    except StopIteration as exc:
        raise KeyError(f"Metric '{metric_key}' has no '{severity}' threshold.") from exc


def metric_threshold_value(metric_key: str, severity: MetricSeverity) -> int | float:
    """Return the numeric value for one explicitly cataloged threshold."""

    return metric_threshold(metric_key, severity).value


def metric_minimum_coverage_pct(metric_key: str) -> float:
    """Return an approved availability-coverage threshold."""

    value = METRIC_CATALOG_BY_KEY[metric_key].availability.minimum_coverage_pct
    if value is None:
        raise KeyError(f"Metric '{metric_key}' has no minimum coverage threshold.")
    return value


_CONFIDENCE_RED_MAX = float(
    metric_threshold_value("release.confidence_score", "critical")
)
_CONFIDENCE_YELLOW_MAX = float(
    metric_threshold_value("release.confidence_score", "watch")
)

RELEASE_THRESHOLD_METADATA = MappingProxyType(
    {
        "open_blockers_red": metric_threshold_value(
            "release.open_blockers", "critical"
        ),
        "open_high_severity_bugs_red": metric_threshold_value(
            "release.open_high_severity_bugs", "critical"
        ),
        "open_high_severity_bugs_yellow": metric_threshold_value(
            "release.open_high_severity_bugs", "watch"
        ),
        "scope_churn_7d_pct_red": metric_threshold_value(
            "release.scope_churn_7d_pct", "critical"
        ),
        "scope_churn_7d_pct_yellow": metric_threshold_value(
            "release.scope_churn_7d_pct", "watch"
        ),
        "reopen_rate_pct_red": metric_threshold_value(
            "release.reopen_rate_pct", "critical"
        ),
        "reopen_rate_pct_yellow": metric_threshold_value(
            "release.reopen_rate_pct", "watch"
        ),
        "median_cycle_time_days_yellow": metric_threshold_value(
            "release.median_cycle_time_days", "watch"
        ),
        "confidence_score_red_max": _CONFIDENCE_RED_MAX,
        # Preserve the existing whole-number API representation of the product
        # rules "greater than 60" and "greater than 90".
        "confidence_score_yellow_min": _CONFIDENCE_RED_MAX + 1.0,
        "confidence_score_yellow_max": _CONFIDENCE_YELLOW_MAX,
        "confidence_score_green_min": _CONFIDENCE_YELLOW_MAX + 1.0,
    }
)


def metrics_for_scope(scope: MetricScope) -> tuple[MetricDefinition, ...]:
    """Return the catalog entries for a scope in deterministic display order."""

    return tuple(metric for metric in METRIC_CATALOG if metric.scope == scope)


def metric_api_fields(
    scope: MetricScope,
    *,
    api_location: MetricApiLocation | None = None,
    chart_participation: bool | None = None,
) -> tuple[str, ...]:
    """Select API field names from the catalog without changing catalog order."""

    definitions = metrics_for_scope(scope)
    return tuple(
        metric.api_field
        for metric in definitions
        if (api_location is None or metric.api_location == api_location)
        and (
            chart_participation is None
            or metric.chart_participation is chart_participation
        )
    )
