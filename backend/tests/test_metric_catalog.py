from dataclasses import FrozenInstanceError
import json
from pathlib import Path

import pytest

from app.metric_catalog import (
    CATALOG_VERSION,
    METRIC_CATALOG,
    METRIC_CATALOG_BY_KEY,
    RELEASE_THRESHOLD_METADATA,
    RELEASE_METRICS,
    SPRINT_METRICS,
    metric_api_fields,
    metric_minimum_coverage_pct,
    metric_threshold,
    metric_threshold_value,
    metrics_for_scope,
)
from app.schemas.metrics import MetricSeries, MetricValues
from app.schemas.sprints import SprintMetricValues
from app.services import (
    analytics_service,
    confidence_breakdown_service,
    metric_availability_service,
    recommendation_engine,
    signal_service,
)
from app.services.metric_availability_service import (
    RELEASE_METRIC_DEPENDENCIES,
    SPRINT_METRIC_DEPENDENCIES,
)
from app.services.metric_catalog_service import MetricCatalogService
from app.services.release_metrics_response_service import (
    RELEASE_CHART_METRIC_NAMES,
    RELEASE_METRIC_NAMES,
)
from app.services.report_template_helpers import (
    format_report_metric_value,
    report_metric_definition,
    report_metric_label,
)
from app.services.sprint_response_service import SPRINT_METRIC_NAMES
from app.utils.constants import RULESET_VERSION


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
FRONTEND_CATALOG_FALLBACK_PATH = (
    REPOSITORY_ROOT / "frontend" / "src" / "generated" / "metricCatalogFallback.json"
)


def _expected_public_metric(metric) -> dict[str, object]:
    return {
        "key": metric.key,
        "scope": metric.scope,
        "api_field": metric.api_field,
        "api_location": metric.api_location,
        "label": metric.label,
        "description": metric.description,
        "category": metric.category,
        "unit": metric.unit,
        "formatting": metric.formatting,
        "display_order": metric.display_order,
        "thresholds": [
            {
                "severity": threshold.severity,
                "comparison": threshold.comparison,
                "value": threshold.value,
                "meaning": threshold.meaning,
            }
            for threshold in metric.thresholds
        ],
        "severity_meaning": metric.severity_meaning,
        "availability": {
            "dependencies": list(metric.availability.dependencies),
            "partial_value_policy": metric.availability.partial_value_policy,
            "supports_not_applicable": metric.availability.supports_not_applicable,
            "evidence_fields": list(metric.availability.evidence_fields),
            "minimum_coverage_pct": metric.availability.minimum_coverage_pct,
        },
        "historical_series": metric.historical_series,
        "signal_participation": metric.signal_participation,
        "confidence_participation": metric.confidence_participation,
        "chart_participation": metric.chart_participation,
        "report_participation": metric.report_participation,
        "ruleset_version": metric.ruleset_version,
    }


def _expected_public_catalog() -> dict[str, object]:
    return {
        "catalog_version": CATALOG_VERSION,
        "ruleset_version": RULESET_VERSION,
        "release": [_expected_public_metric(metric) for metric in RELEASE_METRICS],
        "sprint": [_expected_public_metric(metric) for metric in SPRINT_METRICS],
    }


def test_catalog_covers_every_release_and_sprint_api_metric_exactly_once() -> None:
    release_fields = [metric.api_field for metric in RELEASE_METRICS]
    sprint_fields = [metric.api_field for metric in SPRINT_METRICS]

    assert release_fields == list(MetricSeries.model_fields)
    assert set(MetricValues.model_fields).issubset(release_fields)
    assert sprint_fields == list(SprintMetricValues.model_fields)
    assert len(METRIC_CATALOG) == len(set(metric.key for metric in METRIC_CATALOG))
    assert len(METRIC_CATALOG_BY_KEY) == len(METRIC_CATALOG)


def test_backend_metric_name_inventories_are_catalog_selections() -> None:
    release_value_fields = metric_api_fields("release", api_location="metric_values")
    release_chart_fields = metric_api_fields("release", chart_participation=True)
    sprint_value_fields = metric_api_fields("sprint", api_location="metric_values")

    assert release_value_fields == tuple(MetricValues.model_fields)
    assert release_chart_fields == tuple(MetricSeries.model_fields)
    assert metric_api_fields("release", api_location="response_field") == (
        "confidence_score",
    )
    assert metric_api_fields("release", api_location="chart_only") == (
        "gates_passed_count",
        "readiness_pct",
    )
    assert sprint_value_fields == tuple(SprintMetricValues.model_fields)

    assert RELEASE_METRIC_NAMES == list(release_value_fields)
    assert RELEASE_CHART_METRIC_NAMES == list(release_chart_fields)
    assert SPRINT_METRIC_NAMES == list(sprint_value_fields)


def test_catalog_structure_is_complete_and_deterministically_ordered() -> None:
    assert CATALOG_VERSION == 2
    assert metrics_for_scope("release") == RELEASE_METRICS
    assert metrics_for_scope("sprint") == SPRINT_METRICS

    for scope, definitions in (
        ("release", RELEASE_METRICS),
        ("sprint", SPRINT_METRICS),
    ):
        assert [metric.display_order for metric in definitions] == list(
            range(1, len(definitions) + 1)
        )
        for metric in definitions:
            assert metric.key == f"{scope}.{metric.api_field}"
            assert metric.label
            assert metric.description
            assert metric.severity_meaning
            assert metric.availability.dependencies
            assert metric.availability.evidence_fields
            assert metric.ruleset_version == RULESET_VERSION
            assert METRIC_CATALOG_BY_KEY[metric.key] is metric


def test_public_metadata_serialization_matches_every_catalog_field() -> None:
    public_catalog = MetricCatalogService().get_catalog().model_dump(mode="json")

    assert public_catalog == _expected_public_catalog()


def test_frontend_fallback_is_generated_from_current_public_catalog() -> None:
    generated_text = FRONTEND_CATALOG_FALLBACK_PATH.read_text(encoding="utf-8")
    generated_fallback = json.loads(generated_text)
    expected_text = json.dumps(
        _expected_public_catalog(), indent=2, ensure_ascii=False
    ) + "\n"

    assert generated_fallback == _expected_public_catalog(), (
        "Frontend catalog fallback is stale. Run "
        "`python scripts/export_metric_catalog.py` from backend/."
    )
    assert generated_text == expected_text


def test_catalog_dependencies_match_current_availability_contract() -> None:
    assert {
        metric.api_field: list(metric.availability.dependencies)
        for metric in RELEASE_METRICS
    } == RELEASE_METRIC_DEPENDENCIES
    assert {
        metric.api_field: list(metric.availability.dependencies)
        for metric in SPRINT_METRICS
    } == SPRINT_METRIC_DEPENDENCIES


def test_catalog_and_nested_metadata_are_immutable() -> None:
    with pytest.raises(FrozenInstanceError):
        RELEASE_METRICS[0].label = "Changed"  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        RELEASE_METRICS[0].availability.supports_not_applicable = True  # type: ignore[misc]
    with pytest.raises(TypeError):
        METRIC_CATALOG_BY_KEY["release.open_blockers"] = RELEASE_METRICS[0]  # type: ignore[index]
    with pytest.raises(TypeError):
        RELEASE_THRESHOLD_METADATA["open_blockers_red"] = 99  # type: ignore[index]


def test_threshold_accessors_expose_approved_values_and_coverage() -> None:
    assert metric_threshold("release.open_blockers", "critical").comparison == "gt"
    assert metric_threshold_value("release.open_blockers", "critical") == 0
    assert metric_threshold_value("release.confidence_score", "watch") == 90.0
    assert metric_minimum_coverage_pct("sprint.delivery_confidence_score") == 50.0
    assert metric_minimum_coverage_pct("sprint.workload_concentration_pct") == 50.0

    with pytest.raises(KeyError, match="has no 'watch' threshold"):
        metric_threshold_value("release.open_blockers", "watch")
    with pytest.raises(KeyError, match="has no minimum coverage threshold"):
        metric_minimum_coverage_pct("release.open_blockers")

    assert dict(RELEASE_THRESHOLD_METADATA) == {
        "open_blockers_red": 0,
        "open_high_severity_bugs_red": 1,
        "open_high_severity_bugs_yellow": 0,
        "scope_churn_7d_pct_red": 20.0,
        "scope_churn_7d_pct_yellow": 10.0,
        "reopen_rate_pct_red": 15.0,
        "reopen_rate_pct_yellow": 10.0,
        "median_cycle_time_days_yellow": 7.0,
        "confidence_score_red_max": 60.0,
        "confidence_score_yellow_min": 61.0,
        "confidence_score_yellow_max": 90.0,
        "confidence_score_green_min": 91.0,
    }


def test_threshold_consumers_cannot_drift_from_catalog_values() -> None:
    assert analytics_service.MIN_STORY_POINT_COVERAGE_PCT == (
        metric_minimum_coverage_pct("sprint.delivery_confidence_score")
    )
    assert analytics_service.WORKLOAD_CONCENTRATION_CRITICAL_MIN_EXCLUSIVE_PCT == (
        metric_threshold_value("sprint.workload_concentration_pct", "critical")
    )
    assert analytics_service.WORKLOAD_CONCENTRATION_WATCH_MIN_PCT == (
        metric_threshold_value("sprint.workload_concentration_pct", "watch")
    )
    assert metric_availability_service.MIN_STORY_POINT_COVERAGE_PCT == (
        metric_minimum_coverage_pct("sprint.delivery_confidence_score")
    )

    for module in (
        signal_service,
        confidence_breakdown_service,
    ):
        assert module.OPEN_BLOCKERS_RED_THRESHOLD == metric_threshold_value(
            "release.open_blockers", "critical"
        )
        assert module.HIGH_SEVERITY_BUGS_RED_THRESHOLD == metric_threshold_value(
            "release.open_high_severity_bugs", "critical"
        )
        assert module.HIGH_SEVERITY_BUGS_YELLOW_THRESHOLD == metric_threshold_value(
            "release.open_high_severity_bugs", "watch"
        )
        assert module.SCOPE_CHURN_RED_THRESHOLD * 100 == metric_threshold_value(
            "release.scope_churn_7d_pct", "critical"
        )
        assert module.SCOPE_CHURN_YELLOW_THRESHOLD * 100 == metric_threshold_value(
            "release.scope_churn_7d_pct", "watch"
        )
        assert module.REOPEN_RATE_RED_THRESHOLD * 100 == metric_threshold_value(
            "release.reopen_rate_pct", "critical"
        )
        assert module.REOPEN_RATE_YELLOW_THRESHOLD * 100 == metric_threshold_value(
            "release.reopen_rate_pct", "watch"
        )
        assert module.CYCLE_TIME_YELLOW_THRESHOLD_DAYS == metric_threshold_value(
            "release.median_cycle_time_days", "watch"
        )

    assert recommendation_engine.OPEN_BLOCKERS_RED_THRESHOLD == metric_threshold_value(
        "release.open_blockers", "critical"
    )
    assert recommendation_engine.HIGH_SEVERITY_BUGS_YELLOW_THRESHOLD == (
        metric_threshold_value("release.open_high_severity_bugs", "watch")
    )
    assert recommendation_engine.SCOPE_CHURN_YELLOW_THRESHOLD * 100 == (
        metric_threshold_value("release.scope_churn_7d_pct", "watch")
    )
    assert recommendation_engine.REOPEN_RATE_YELLOW_THRESHOLD * 100 == (
        metric_threshold_value("release.reopen_rate_pct", "watch")
    )
    assert recommendation_engine.CYCLE_TIME_YELLOW_THRESHOLD_DAYS == (
        metric_threshold_value("release.median_cycle_time_days", "watch")
    )
    assert recommendation_engine.WORKLOAD_CONCENTRATION_WATCH_MIN_PCT == (
        metric_threshold_value("sprint.workload_concentration_pct", "watch")
    )


def test_report_presentation_uses_catalog_labels_units_and_evidence() -> None:
    assert report_metric_label("release.scope_churn_7d_pct") == "Scope churn 7d"
    assert report_metric_label("sprint.committed_scope") == "Current sprint scope"
    assert format_report_metric_value("release.open_blockers", 2) == "2"
    assert format_report_metric_value("release.scope_churn_7d_pct", 12.5) == "12.50%"
    assert (
        format_report_metric_value("sprint.median_cycle_time_days", 3.125)
        == "3.1250 days"
    )
    assert (
        format_report_metric_value(
            "sprint.median_cycle_time_days", 3.125, include_unit=False
        )
        == "3.1250"
    )
    assert format_report_metric_value("release.confidence_score", 72) == "72.0%"
    assert format_report_metric_value("sprint.delivery_confidence_score", 72) == "72.00%"

    definition = report_metric_definition("sprint.reopen_rate_pct")
    assert definition.api_field == "reopen_rate_pct"
    assert definition.availability.evidence_fields == (
        "calculation_provenance.metric_evidence.reopen_rate_pct",
    )

    for metric in METRIC_CATALOG:
        if metric.report_participation:
            assert report_metric_definition(metric.key) is metric
            assert report_metric_label(metric.key) == metric.label
        else:
            with pytest.raises(ValueError, match="does not participate in reports"):
                report_metric_definition(metric.key)


def test_only_product_rule_thresholds_are_cataloged() -> None:
    assert [
        (item.severity, item.comparison, item.value)
        for item in METRIC_CATALOG_BY_KEY["release.open_blockers"].thresholds
    ] == [("critical", "gt", 0.0)]
    assert [
        (item.severity, item.comparison, item.value)
        for item in METRIC_CATALOG_BY_KEY["release.open_high_severity_bugs"].thresholds
    ] == [
        ("critical", "gt", 1.0),
        ("watch", "gt", 0.0),
    ]
    assert [
        (item.severity, item.comparison, item.value)
        for item in METRIC_CATALOG_BY_KEY["release.scope_churn_7d_pct"].thresholds
    ] == [
        ("critical", "gt", 20.0),
        ("watch", "gt", 10.0),
    ]
    assert [
        (item.severity, item.comparison, item.value)
        for item in METRIC_CATALOG_BY_KEY["release.reopen_rate_pct"].thresholds
    ] == [
        ("critical", "gt", 15.0),
        ("watch", "gt", 10.0),
    ]
    assert [
        (item.severity, item.comparison, item.value)
        for item in METRIC_CATALOG_BY_KEY["release.median_cycle_time_days"].thresholds
    ] == [("watch", "gt", 7.0)]
    assert [
        (item.severity, item.comparison, item.value)
        for item in METRIC_CATALOG_BY_KEY["release.confidence_score"].thresholds
    ] == [
        ("critical", "lte", 60.0),
        ("watch", "lte", 90.0),
    ]
    assert [
        (item.severity, item.comparison, item.value)
        for item in METRIC_CATALOG_BY_KEY[
            "sprint.workload_concentration_pct"
        ].thresholds
    ] == [
        ("critical", "gt", 50.0),
        ("watch", "gte", 35.0),
    ]
    assert [
        (item.severity, item.comparison, item.value)
        for item in METRIC_CATALOG_BY_KEY["sprint.scope_creep_pct"].thresholds
    ] == [
        ("critical", "gt", 20.0),
        ("watch", "gt", 10.0),
    ]

    thresholded_keys = {metric.key for metric in METRIC_CATALOG if metric.thresholds}
    assert thresholded_keys == {
        "release.open_blockers",
        "release.open_high_severity_bugs",
        "release.scope_churn_7d_pct",
        "release.median_cycle_time_days",
        "release.reopen_rate_pct",
        "release.confidence_score",
        "sprint.scope_creep_pct",
        "sprint.workload_concentration_pct",
    }
