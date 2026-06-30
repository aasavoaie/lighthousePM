import type { ReleaseChartsResponse, ReleaseMetricsResponse } from "../api/types";
import {
  getReleaseChartEmptyMessage,
  getReleaseMetricDisplay,
  getReleaseScoreDisplay,
} from "./releaseAvailability";

function assertEqual<T>(actual: T, expected: T, message: string) {
  if (actual !== expected) {
    throw new Error(`${message}: expected ${String(expected)}, received ${String(actual)}`);
  }
}

function metricsResponse(overrides: Partial<ReleaseMetricsResponse> = {}): ReleaseMetricsResponse {
  return {
    release_id: "REL-1",
    snapshot_at: "2026-06-01T10:00:00Z",
    computation_status: "COMPUTED",
    unavailable_reason: null,
    metrics: {
      open_blockers: 0,
      open_high_severity_bugs: 0,
      scope_completed_pct: 75,
      completed_tickets: 3,
      scope_churn_7d_pct: 0,
      scope_added_7d_count: 0,
      scope_removed_7d_count: 0,
      median_cycle_time_days: 2,
      reopen_rate_pct: 0,
    },
    metric_issue_keys: {
      open_blockers: [],
      open_high_severity_bugs: [],
    },
    metric_names: [],
    metric_availability: {
      context: {
        has_tickets: true,
        has_story_points: true,
        has_completed_tickets: true,
        has_release_scope: true,
        has_sprint_scope: false,
        has_changelog: true,
      },
      metrics: {},
    },
    metric_thresholds: null,
    confidence_score: 88,
    confidence_breakdown: null,
    biggest_driver: null,
    recommendations: [],
    is_computed: true,
    snapshot_age_hours: 1,
    ...overrides,
  };
}

function chartsResponse(overrides: Partial<ReleaseChartsResponse> = {}): ReleaseChartsResponse {
  return {
    release_id: "REL-1",
    metric_names: [],
    point_count: 1,
    release_gates_total: 5,
    series: {
      open_blockers: [],
      open_high_severity_bugs: [],
      scope_completed_pct: [],
      completed_tickets: [],
      scope_churn_7d_pct: [],
      scope_added_7d_count: [],
      scope_removed_7d_count: [],
      median_cycle_time_days: [],
      reopen_rate_pct: [],
      confidence_score: [{ snapshot_at: "2026-06-01T10:00:00Z", value: null }],
      gates_passed_count: [],
      readiness_pct: [{ snapshot_at: "2026-06-01T10:00:00Z", value: null }],
    },
    ...overrides,
  };
}

const noTicketMetrics = metricsResponse({
  computation_status: "NOT_COMPUTED",
  unavailable_reason: "No tickets are available for this scope.",
  confidence_score: null,
  metric_availability: {
    context: {
      has_tickets: false,
      has_story_points: false,
      has_completed_tickets: false,
      has_release_scope: false,
      has_sprint_scope: false,
      has_changelog: false,
    },
    metrics: {
      scope_completed_pct: {
        available: false,
        reason: "No tickets are available for this scope.",
        depends_on: ["ticket_count", "release_assignment"],
      },
    },
  },
});
const noTicketCharts = chartsResponse();

const scoreDisplay = getReleaseScoreDisplay(noTicketMetrics);
assertEqual(scoreDisplay.value, "Not enough data", "zero-ticket release score card shows unavailable copy");
assertEqual(scoreDisplay.reason, "No tickets are available for this scope.", "zero-ticket score card uses API reason");
assertEqual(scoreDisplay.isAvailable, false, "zero-ticket score card is unavailable");

const metricDisplay = getReleaseMetricDisplay(noTicketMetrics, "scope_completed_pct");
assertEqual(metricDisplay.value, "N/A", "unavailable metric card displays N/A");
assertEqual(metricDisplay.badge, "No tickets", "unavailable metric card shows no-ticket badge");
assertEqual(metricDisplay.reason, "No tickets are available for this scope.", "unavailable metric card exposes reason");

const noStoryPointMetricDisplay = getReleaseMetricDisplay(
  metricsResponse({
    metric_availability: {
      context: {
        has_tickets: true,
        has_story_points: false,
        has_completed_tickets: true,
        has_release_scope: true,
        has_sprint_scope: false,
        has_changelog: true,
      },
      metrics: {
        scope_completed_pct: {
          available: false,
          reason: "No tickets in this scope have story points.",
          depends_on: ["ticket_count", "story_points", "release_assignment"],
        },
      },
    },
  }),
  "scope_completed_pct"
);
assertEqual(noStoryPointMetricDisplay.badge, "No story points", "story-point unavailable metric shows story-point badge");

assertEqual(
  noTicketCharts.series.confidence_score.some((point) => point.value !== null),
  false,
  "unavailable confidence chart has no computable points"
);
assertEqual(
  noTicketCharts.series.readiness_pct.some((point) => point.value !== null),
  false,
  "unavailable readiness chart has no computable progress points"
);
assertEqual(
  getReleaseChartEmptyMessage(
    noTicketMetrics,
    noTicketCharts,
    "confidence_score",
    "No confidence history available yet."
  ),
  "No tickets are available for this scope.",
  "confidence chart empty state uses API reason when not computable"
);
assertEqual(
  getReleaseChartEmptyMessage(
    noTicketMetrics,
    noTicketCharts,
    "readiness_pct",
    "No readiness history available yet."
  ),
  "No tickets are available for this scope.",
  "readiness chart empty state uses API reason when not computable"
);
assertEqual(
  getReleaseChartEmptyMessage(
    metricsResponse(),
    chartsResponse({
      series: {
        ...chartsResponse().series,
        confidence_score: [{ snapshot_at: "2026-06-01T10:00:00Z", value: 88 }],
      },
    }),
    "confidence_score",
    "No confidence history available yet."
  ),
  "No confidence history available yet.",
  "computed confidence chart keeps default empty copy"
);
