import type { MetricCatalogResponse, MetricDefinitionMetadata } from "./api/types";
import {
  catalogMetricStatus,
  fallbackMetricCatalog,
  formatCatalogMetricValue,
  metricDefinition,
  resolveMetricCatalog,
} from "./metricCatalog";

function assertEqual<T>(actual: T, expected: T, message: string) {
  if (actual !== expected) {
    throw new Error(`${message}: expected ${String(expected)}, received ${String(actual)}`);
  }
}

function apiMetric(
  metric: (typeof fallbackMetricCatalog.release)[number] | (typeof fallbackMetricCatalog.sprint)[number],
): MetricDefinitionMetadata {
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

assertEqual(fallbackMetricCatalog.release.length, 12, "fallback release inventory is complete");
assertEqual(fallbackMetricCatalog.sprint.length, 12, "fallback sprint inventory is complete");
assertEqual(fallbackMetricCatalog.source, "fallback", "fallback source is explicit");
assertEqual(fallbackMetricCatalog.catalogVersion, 1, "generated fallback catalog version is retained");
assertEqual(fallbackMetricCatalog.rulesetVersion, 2, "generated fallback ruleset version is retained");
assertEqual(
  fallbackMetricCatalog.release.map((metric) => metric.api_field).join(","),
  "open_blockers,open_high_severity_bugs,scope_completed_pct,completed_tickets,scope_churn_7d_pct,scope_added_7d_count,scope_removed_7d_count,median_cycle_time_days,reopen_rate_pct,confidence_score,gates_passed_count,readiness_pct",
  "fallback release order matches the API contract",
);
assertEqual(
  fallbackMetricCatalog.sprint.map((metric) => metric.api_field).join(","),
  "committed_scope,completed_scope_pct,open_blockers,open_high_severity_bugs,bugs_created_during_sprint,in_progress_count,not_started_count,rollover_count,median_cycle_time_days,reopen_rate_pct,workload_concentration_pct,delivery_confidence_score",
  "fallback sprint order matches the API contract",
);

const blockers = metricDefinition(fallbackMetricCatalog, "release", "open_blockers");
assertEqual(blockers.label, "Open blockers", "fallback label is deterministic");
assertEqual(formatCatalogMetricValue(blockers, 2), "2", "integer formatting comes from catalog");
assertEqual(catalogMetricStatus(blockers, 0), "good", "healthy threshold value");
assertEqual(catalogMetricStatus(blockers, 1), "critical", "critical threshold value");

const releaseChurn = metricDefinition(fallbackMetricCatalog, "release", "scope_churn_7d_pct");
assertEqual(formatCatalogMetricValue(releaseChurn, 12.5), "12.50%", "percent formatting comes from catalog");
assertEqual(catalogMetricStatus(releaseChurn, 10), "good", "strict watch boundary is respected");
assertEqual(catalogMetricStatus(releaseChurn, 10.01), "warning", "watch comparison is respected");
assertEqual(catalogMetricStatus(releaseChurn, 20.01), "critical", "critical comparison is respected");

const cycleTime = metricDefinition(fallbackMetricCatalog, "sprint", "median_cycle_time_days");
assertEqual(formatCatalogMetricValue(cycleTime, 3.125), "3.1250", "decimal precision comes from catalog");
const workload = metricDefinition(fallbackMetricCatalog, "sprint", "workload_concentration_pct");
assertEqual(workload.availability.minimum_coverage_pct, 50, "fallback availability coverage is explicit");

const apiResponse: MetricCatalogResponse = {
  catalog_version: 4,
  ruleset_version: 8,
  release: fallbackMetricCatalog.release.map(apiMetric).reverse(),
  sprint: fallbackMetricCatalog.sprint.map(apiMetric).reverse(),
};
apiResponse.release[0] = { ...apiResponse.release[0], label: "API readiness label" };
apiResponse.sprint[1] = {
  ...apiResponse.sprint[1],
  availability: {
    ...apiResponse.sprint[1].availability,
    minimum_coverage_pct: 75,
  },
};
const apiCatalog = resolveMetricCatalog(apiResponse);
assertEqual(apiCatalog.source, "api", "valid API metadata replaces fallback");
assertEqual(apiCatalog.catalogVersion, 4, "API catalog version is retained");
assertEqual(apiCatalog.release[0].display_order, 1, "API entries are ordered deterministically");
assertEqual(
  metricDefinition(apiCatalog, "release", "readiness_pct").label,
  "API readiness label",
  "API label is authoritative",
);
assertEqual(
  metricDefinition(apiCatalog, "sprint", apiResponse.sprint[1].api_field).availability.minimum_coverage_pct,
  75,
  "API availability metadata is authoritative",
);

assertEqual(resolveMetricCatalog(null), fallbackMetricCatalog, "missing response uses fallback");
assertEqual(
  resolveMetricCatalog({ ...apiResponse, release: apiResponse.release.slice(1) }),
  fallbackMetricCatalog,
  "incomplete response uses fallback",
);
assertEqual(
  resolveMetricCatalog({
    ...apiResponse,
    sprint: [...apiResponse.sprint, apiResponse.sprint[0]],
  }),
  fallbackMetricCatalog,
  "duplicate response entries use fallback",
);
assertEqual(
  resolveMetricCatalog({
    ...apiResponse,
    release: apiResponse.release.map((metric, index) => (
      index === 0 ? { ...metric, formatting: "unsupported" } : metric
    )),
  }),
  fallbackMetricCatalog,
  "incompatible presentation metadata uses fallback",
);
assertEqual(
  resolveMetricCatalog({
    ...apiResponse,
    sprint: apiResponse.sprint.map((metric, index) => (
      index === 0 ? { ...metric, ruleset_version: 7 } : metric
    )),
  }),
  fallbackMetricCatalog,
  "per-metric ruleset drift uses fallback",
);
