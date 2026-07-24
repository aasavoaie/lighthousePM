import type {
  MetricCatalogResponse,
  MetricDefinitionMetadata,
  MetricScope,
  MetricThresholdMetadata,
} from "./api/types";
import generatedMetricCatalog from "./generated/metricCatalogFallback.json";

export interface MetricCatalogView {
  catalogVersion: number;
  rulesetVersion: number;
  source: "api" | "fallback";
  release: readonly MetricPresentationDefinition[];
  sprint: readonly MetricPresentationDefinition[];
  byKey: Readonly<Record<string, MetricPresentationDefinition>>;
}

export type MetricPresentationDefinition = Pick<
  MetricDefinitionMetadata,
  | "key"
  | "scope"
  | "api_field"
  | "api_location"
  | "label"
  | "description"
  | "category"
  | "unit"
  | "formatting"
  | "display_order"
  | "thresholds"
  | "historical_series"
  | "chart_participation"
> & {
  availability: Pick<
    MetricDefinitionMetadata["availability"],
    "partial_value_policy" | "supports_not_applicable" | "minimum_coverage_pct"
  >;
};

const fallbackResponse = generatedMetricCatalog as MetricCatalogResponse;
const releaseFallback = fallbackResponse.release;
const sprintFallback = fallbackResponse.sprint;

const validApiLocations = new Set(["metric_values", "response_field", "chart_only"]);
const validCategories = new Set(["delivery", "quality", "flow", "risk", "snapshot"]);
const validUnits = new Set(["tickets", "percent", "days", "score", "gates"]);
const validFormatting = new Set(["integer", "decimal_1", "decimal_2", "decimal_4", "percent_2"]);
const validPartialValuePolicies = new Set([
  "confirmed_minimum",
  "calculated_from_available_data",
  "unavailable",
  "not_supported",
]);

function isStringArray(value: unknown): value is string[] {
  return Array.isArray(value) && value.every((item) => typeof item === "string");
}

function isValidThreshold(value: unknown): value is MetricThresholdMetadata {
  if (!value || typeof value !== "object") {
    return false;
  }
  const threshold = value as Partial<MetricThresholdMetadata>;
  return (threshold.severity === "watch" || threshold.severity === "critical")
    && ["gt", "gte", "lt", "lte"].includes(threshold.comparison ?? "")
    && typeof threshold.value === "number"
    && Number.isFinite(threshold.value)
    && typeof threshold.meaning === "string"
    && threshold.meaning.length > 0;
}

function buildView(
  release: readonly MetricPresentationDefinition[],
  sprint: readonly MetricPresentationDefinition[],
  catalogVersion: number,
  rulesetVersion: number,
  source: MetricCatalogView["source"],
): MetricCatalogView {
  const orderedRelease = [...release].sort((left, right) => left.display_order - right.display_order);
  const orderedSprint = [...sprint].sort((left, right) => left.display_order - right.display_order);
  return {
    catalogVersion,
    rulesetVersion,
    source,
    release: orderedRelease,
    sprint: orderedSprint,
    byKey: Object.fromEntries([...orderedRelease, ...orderedSprint].map((metric) => [metric.key, metric])),
  };
}

export const fallbackMetricCatalog = buildView(
  releaseFallback,
  sprintFallback,
  fallbackResponse.catalog_version,
  fallbackResponse.ruleset_version,
  "fallback",
);

function isValidDefinition(
  value: unknown,
  scope: MetricScope,
  expected: MetricPresentationDefinition,
  rulesetVersion: number,
): value is MetricDefinitionMetadata {
  if (!value || typeof value !== "object") {
    return false;
  }
  const definition = value as Partial<MetricDefinitionMetadata>;
  const availability = definition.availability;
  return definition.scope === scope
    && typeof definition.api_field === "string"
    && definition.key === `${scope}.${definition.api_field}`
    && definition.api_location === expected.api_location
    && typeof definition.label === "string"
    && definition.label.length > 0
    && typeof definition.description === "string"
    && definition.description.length > 0
    && validCategories.has(definition.category ?? "")
    && validUnits.has(definition.unit ?? "")
    && validFormatting.has(definition.formatting ?? "")
    && Number.isInteger(definition.display_order)
    && Array.isArray(definition.thresholds)
    && definition.thresholds.every(isValidThreshold)
    && typeof definition.severity_meaning === "string"
    && definition.severity_meaning.length > 0
    && Boolean(availability)
    && isStringArray(availability?.dependencies)
    && validPartialValuePolicies.has(availability?.partial_value_policy ?? "")
    && typeof availability?.supports_not_applicable === "boolean"
    && isStringArray(availability?.evidence_fields)
    && (availability?.minimum_coverage_pct === null
      || (typeof availability?.minimum_coverage_pct === "number"
        && Number.isFinite(availability.minimum_coverage_pct)))
    && typeof definition.historical_series === "boolean"
    && typeof definition.signal_participation === "boolean"
    && typeof definition.confidence_participation === "boolean"
    && typeof definition.chart_participation === "boolean"
    && typeof definition.report_participation === "boolean"
    && definition.ruleset_version === rulesetVersion;
}

function isCompleteScope(
  definitions: MetricDefinitionMetadata[],
  scope: MetricScope,
  fallback: readonly MetricPresentationDefinition[],
  rulesetVersion: number,
) {
  if (definitions.length !== fallback.length) {
    return false;
  }
  const expectedFields = new Set(fallback.map((metric) => metric.api_field));
  const actualFields = new Set(definitions.map((metric) => metric.api_field));
  const displayOrder = definitions.map((metric) => metric.display_order).sort((left, right) => left - right);
  const expectedByField = Object.fromEntries(
    fallback.map((metric) => [metric.api_field, metric]),
  );
  return definitions.every((metric) => (
    Boolean(expectedByField[metric.api_field])
    && isValidDefinition(metric, scope, expectedByField[metric.api_field], rulesetVersion)
  ))
    && expectedFields.size === actualFields.size
    && [...expectedFields].every((field) => actualFields.has(field))
    && displayOrder.every((value, index) => value === index + 1);
}

export function resolveMetricCatalog(value: unknown): MetricCatalogView {
  if (!value || typeof value !== "object") {
    return fallbackMetricCatalog;
  }
  const response = value as Partial<MetricCatalogResponse>;
  if (
    typeof response.catalog_version !== "number"
    || !Number.isInteger(response.catalog_version)
    || response.catalog_version < 1
    || typeof response.ruleset_version !== "number"
    || !Number.isInteger(response.ruleset_version)
    || response.ruleset_version < 1
    || !Array.isArray(response.release)
    || !Array.isArray(response.sprint)
    || !isCompleteScope(response.release, "release", releaseFallback, response.ruleset_version)
    || !isCompleteScope(response.sprint, "sprint", sprintFallback, response.ruleset_version)
  ) {
    return fallbackMetricCatalog;
  }
  const keys = [...response.release, ...response.sprint].map((metric) => metric.key);
  if (new Set(keys).size !== keys.length) {
    return fallbackMetricCatalog;
  }
  return buildView(
    response.release,
    response.sprint,
    response.catalog_version,
    response.ruleset_version,
    "api",
  );
}

export function metricDefinition(
  catalog: MetricCatalogView,
  scope: MetricScope,
  apiField: string,
): MetricPresentationDefinition {
  return catalog.byKey[`${scope}.${apiField}`]
    ?? fallbackMetricCatalog.byKey[`${scope}.${apiField}`];
}

export function formatCatalogMetricValue(
  definition: MetricPresentationDefinition,
  value: number | null,
): string {
  if (value === null) {
    return "N/A";
  }
  switch (definition.formatting) {
    case "integer":
      return String(Math.round(value));
    case "decimal_1":
      return value.toFixed(1);
    case "decimal_2":
      return value.toFixed(2);
    case "decimal_4":
      return value.toFixed(4);
    case "percent_2":
      return `${value.toFixed(2)}%`;
  }
}

function thresholdMatches(threshold: MetricThresholdMetadata, value: number): boolean {
  switch (threshold.comparison) {
    case "gt":
      return value > threshold.value;
    case "gte":
      return value >= threshold.value;
    case "lt":
      return value < threshold.value;
    case "lte":
      return value <= threshold.value;
  }
}

export function catalogMetricStatus(
  definition: MetricPresentationDefinition,
  value: number | null,
): "good" | "warning" | "critical" | "neutral" {
  if (value === null || definition.thresholds.length === 0) {
    return "neutral";
  }
  for (const threshold of definition.thresholds) {
    if (thresholdMatches(threshold, value)) {
      return threshold.severity === "critical" ? "critical" : "warning";
    }
  }
  return "good";
}
