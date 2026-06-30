import type { MetricValues, ReleaseChartsResponse, ReleaseMetricsResponse } from "../api/types";

export const NO_TICKETS_REASON = "No tickets are available for this scope.";
export const NO_STORY_POINTS_REASON = "No tickets in this scope have story points.";

export function hasComputableReleaseConfidence(metrics: ReleaseMetricsResponse | null) {
  return metrics?.computation_status !== "NOT_COMPUTED" && metrics?.confidence_score !== null;
}

export function getReleaseScoreDisplay(metrics: ReleaseMetricsResponse | null) {
  if (metrics?.computation_status === "NOT_COMPUTED") {
    return {
      value: "Not enough data",
      label: "Confidence",
      reason: metrics.unavailable_reason ?? NO_TICKETS_REASON,
      isAvailable: false,
    };
  }
  return {
    value: null,
    label: "Confidence",
    reason: null,
    isAvailable: true,
  };
}

export function getReleaseMetricAvailability(
  metrics: ReleaseMetricsResponse | null,
  metricName: keyof MetricValues
) {
  return metrics?.metric_availability?.metrics[metricName] ?? null;
}

export function getReleaseMetricUnavailableBadge(reason: string | null | undefined) {
  if (!reason) {
    return null;
  }
  if (reason === NO_STORY_POINTS_REASON) {
    return "No story points";
  }
  if (reason === NO_TICKETS_REASON) {
    return "No tickets";
  }
  return "Unavailable";
}

export function getReleaseMetricDisplay(
  metrics: ReleaseMetricsResponse | null,
  metricName: keyof MetricValues
) {
  const availability = getReleaseMetricAvailability(metrics, metricName);
  if (availability && !availability.available) {
    return {
      value: "N/A",
      badge: getReleaseMetricUnavailableBadge(availability.reason),
      reason: availability.reason,
      isAvailable: false,
    };
  }
  return {
    value: null,
    badge: null,
    reason: null,
    isAvailable: true,
  };
}

export function getReleaseChartEmptyMessage(
  metrics: ReleaseMetricsResponse | null,
  charts: ReleaseChartsResponse | null,
  metricName: "confidence_score" | "readiness_pct",
  defaultMessage: string
) {
  const points = charts?.series[metricName] ?? [];
  const hasComputablePoints = points.some((point) => point.value !== null);
  if (hasComputablePoints) {
    return defaultMessage;
  }
  if (metrics?.computation_status === "NOT_COMPUTED") {
    return metrics.unavailable_reason ?? NO_TICKETS_REASON;
  }
  return defaultMessage;
}
