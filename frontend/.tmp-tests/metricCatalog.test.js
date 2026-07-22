"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
const metricCatalog_1 = require("./metricCatalog");
function assertEqual(actual, expected, message) {
    if (actual !== expected) {
        throw new Error(`${message}: expected ${String(expected)}, received ${String(actual)}`);
    }
}
function apiMetric(metric) {
    return {
        ...metric,
        severity_meaning: "Test severity meaning.",
        availability: {
            ...metric.availability,
            dependencies: ["ticket_count"],
            evidence_fields: ["calculation_provenance.metric_evidence"],
        },
        historical_series: false,
        signal_participation: false,
        confidence_participation: false,
        chart_participation: false,
        report_participation: false,
        ruleset_version: 8,
    };
}
assertEqual(metricCatalog_1.fallbackMetricCatalog.release.length, 12, "fallback release inventory is complete");
assertEqual(metricCatalog_1.fallbackMetricCatalog.sprint.length, 12, "fallback sprint inventory is complete");
assertEqual(metricCatalog_1.fallbackMetricCatalog.source, "fallback", "fallback source is explicit");
assertEqual(metricCatalog_1.fallbackMetricCatalog.catalogVersion, 1, "generated fallback catalog version is retained");
assertEqual(metricCatalog_1.fallbackMetricCatalog.rulesetVersion, 2, "generated fallback ruleset version is retained");
assertEqual(metricCatalog_1.fallbackMetricCatalog.release.map((metric) => metric.api_field).join(","), "open_blockers,open_high_severity_bugs,scope_completed_pct,completed_tickets,scope_churn_7d_pct,scope_added_7d_count,scope_removed_7d_count,median_cycle_time_days,reopen_rate_pct,confidence_score,gates_passed_count,readiness_pct", "fallback release order matches the API contract");
assertEqual(metricCatalog_1.fallbackMetricCatalog.sprint.map((metric) => metric.api_field).join(","), "committed_scope,completed_scope_pct,open_blockers,open_high_severity_bugs,bugs_created_during_sprint,in_progress_count,not_started_count,rollover_count,median_cycle_time_days,reopen_rate_pct,workload_concentration_pct,delivery_confidence_score", "fallback sprint order matches the API contract");
const blockers = (0, metricCatalog_1.metricDefinition)(metricCatalog_1.fallbackMetricCatalog, "release", "open_blockers");
assertEqual(blockers.label, "Open blockers", "fallback label is deterministic");
assertEqual((0, metricCatalog_1.formatCatalogMetricValue)(blockers, 2), "2", "integer formatting comes from catalog");
assertEqual((0, metricCatalog_1.catalogMetricStatus)(blockers, 0), "good", "healthy threshold value");
assertEqual((0, metricCatalog_1.catalogMetricStatus)(blockers, 1), "critical", "critical threshold value");
const releaseChurn = (0, metricCatalog_1.metricDefinition)(metricCatalog_1.fallbackMetricCatalog, "release", "scope_churn_7d_pct");
assertEqual((0, metricCatalog_1.formatCatalogMetricValue)(releaseChurn, 12.5), "12.50%", "percent formatting comes from catalog");
assertEqual((0, metricCatalog_1.catalogMetricStatus)(releaseChurn, 10), "good", "strict watch boundary is respected");
assertEqual((0, metricCatalog_1.catalogMetricStatus)(releaseChurn, 10.01), "warning", "watch comparison is respected");
assertEqual((0, metricCatalog_1.catalogMetricStatus)(releaseChurn, 20.01), "critical", "critical comparison is respected");
const cycleTime = (0, metricCatalog_1.metricDefinition)(metricCatalog_1.fallbackMetricCatalog, "sprint", "median_cycle_time_days");
assertEqual((0, metricCatalog_1.formatCatalogMetricValue)(cycleTime, 3.125), "3.1250", "decimal precision comes from catalog");
const workload = (0, metricCatalog_1.metricDefinition)(metricCatalog_1.fallbackMetricCatalog, "sprint", "workload_concentration_pct");
assertEqual(workload.availability.minimum_coverage_pct, 50, "fallback availability coverage is explicit");
const apiResponse = {
    catalog_version: 4,
    ruleset_version: 8,
    release: metricCatalog_1.fallbackMetricCatalog.release.map(apiMetric).reverse(),
    sprint: metricCatalog_1.fallbackMetricCatalog.sprint.map(apiMetric).reverse(),
};
apiResponse.release[0] = { ...apiResponse.release[0], label: "API readiness label" };
apiResponse.sprint[1] = {
    ...apiResponse.sprint[1],
    availability: {
        ...apiResponse.sprint[1].availability,
        minimum_coverage_pct: 75,
    },
};
const apiCatalog = (0, metricCatalog_1.resolveMetricCatalog)(apiResponse);
assertEqual(apiCatalog.source, "api", "valid API metadata replaces fallback");
assertEqual(apiCatalog.catalogVersion, 4, "API catalog version is retained");
assertEqual(apiCatalog.release[0].display_order, 1, "API entries are ordered deterministically");
assertEqual((0, metricCatalog_1.metricDefinition)(apiCatalog, "release", "readiness_pct").label, "API readiness label", "API label is authoritative");
assertEqual((0, metricCatalog_1.metricDefinition)(apiCatalog, "sprint", apiResponse.sprint[1].api_field).availability.minimum_coverage_pct, 75, "API availability metadata is authoritative");
assertEqual((0, metricCatalog_1.resolveMetricCatalog)(null), metricCatalog_1.fallbackMetricCatalog, "missing response uses fallback");
assertEqual((0, metricCatalog_1.resolveMetricCatalog)({ ...apiResponse, release: apiResponse.release.slice(1) }), metricCatalog_1.fallbackMetricCatalog, "incomplete response uses fallback");
assertEqual((0, metricCatalog_1.resolveMetricCatalog)({
    ...apiResponse,
    sprint: [...apiResponse.sprint, apiResponse.sprint[0]],
}), metricCatalog_1.fallbackMetricCatalog, "duplicate response entries use fallback");
assertEqual((0, metricCatalog_1.resolveMetricCatalog)({
    ...apiResponse,
    release: apiResponse.release.map((metric, index) => (index === 0 ? { ...metric, formatting: "unsupported" } : metric)),
}), metricCatalog_1.fallbackMetricCatalog, "incompatible presentation metadata uses fallback");
assertEqual((0, metricCatalog_1.resolveMetricCatalog)({
    ...apiResponse,
    sprint: apiResponse.sprint.map((metric, index) => (index === 0 ? { ...metric, ruleset_version: 7 } : metric)),
}), metricCatalog_1.fallbackMetricCatalog, "per-metric ruleset drift uses fallback");
