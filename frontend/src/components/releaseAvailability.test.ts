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
    ruleset_version: overrides.ruleset_version ?? 1,
    ruleset_label: overrides.ruleset_label ?? "Ruleset v1",
    calculation_provenance: overrides.calculation_provenance ?? {},
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
      confidence_score: [{ snapshot_at: "2026-06-01T10:00:00Z", value: null, ruleset_version: 1, version_boundary: false }],
      gates_passed_count: [],
      readiness_pct: [{ snapshot_at: "2026-06-01T10:00:00Z", value: null, ruleset_version: 1, version_boundary: false }],
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
        status: "NOT_COMPUTED",
        available: false,
        reason: "No tickets are available for this scope.",
        explanations: ["No tickets are available for this scope."],
        missing_issue_keys: [],
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

const partialReason = "Open blockers are a confirmed minimum because classification is incomplete.";
const partialMetrics = metricsResponse({
  computation_status: "PARTIAL",
  unavailable_reason: partialReason,
  confidence_score: null,
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
      open_blockers: {
        status: "PARTIAL",
        available: true,
        reason: partialReason,
        explanations: [partialReason],
        missing_issue_keys: ["LHPM-1"],
        depends_on: ["ticket_count", "release_assignment"],
      },
      scope_completed_pct: {
        status: "PARTIAL",
        available: false,
        reason: "Scope completed is unavailable because one ticket has no status.",
        explanations: ["Scope completed is unavailable because one ticket has no status."],
        missing_issue_keys: ["LHPM-2"],
        depends_on: ["ticket_count", "release_assignment"],
      },
    },
  },
});
const partialCountDisplay = getReleaseMetricDisplay(partialMetrics, "open_blockers");
assertEqual(partialCountDisplay.badge, "Partial", "confirmed-minimum metric shows a partial badge");
assertEqual(partialCountDisplay.isAvailable, true, "confirmed-minimum count remains available");
const partialScopeDisplay = getReleaseMetricDisplay(partialMetrics, "scope_completed_pct");
assertEqual(partialScopeDisplay.badge, "Partial", "unavailable partial percentage shows a partial badge");
assertEqual(partialScopeDisplay.isAvailable, false, "partial percentage remains unavailable");
const partialScoreDisplay = getReleaseScoreDisplay(partialMetrics);
assertEqual(partialScoreDisplay.value, "Inconclusive", "partial release confidence is inconclusive");
assertEqual(partialScoreDisplay.isAvailable, false, "partial release confidence is unavailable");

const partialChurnReason =
  "Scope churn is partial because Jira changelog ingestion is incomplete for 1 project ticket(s). Addition and removal event counts are confirmed minima; the percentage is unavailable.";
const partialChurnMetrics = metricsResponse({
  computation_status: "PARTIAL",
  unavailable_reason: partialChurnReason,
  confidence_score: null,
  metrics: {
    ...metricsResponse().metrics,
    scope_churn_7d_pct: null,
    scope_added_7d_count: 2,
    scope_removed_7d_count: 1,
  },
  metric_availability: {
    ...metricsResponse().metric_availability!,
    metrics: {
      ...metricsResponse().metric_availability!.metrics,
      scope_churn_7d_pct: {
        status: "PARTIAL",
        available: false,
        reason: partialChurnReason,
        explanations: [partialChurnReason],
        missing_issue_keys: ["LHPM-9"],
        depends_on: ["project_changelog_completeness", "observed_release_scope"],
      },
      scope_added_7d_count: {
        status: "PARTIAL",
        available: true,
        reason: partialChurnReason,
        explanations: [partialChurnReason],
        missing_issue_keys: ["LHPM-9"],
        depends_on: ["project_changelog_completeness", "observed_release_scope"],
      },
    },
  },
});
const partialChurnDisplay = getReleaseMetricDisplay(partialChurnMetrics, "scope_churn_7d_pct");
assertEqual(partialChurnDisplay.badge, "Partial", "partial churn percentage shows a partial badge");
assertEqual(partialChurnDisplay.isAvailable, false, "partial churn percentage remains unavailable");
assertEqual(partialChurnDisplay.reason, partialChurnReason, "partial churn explains incomplete history");
const partialAddedDisplay = getReleaseMetricDisplay(partialChurnMetrics, "scope_added_7d_count");
assertEqual(partialAddedDisplay.badge, "Partial", "confirmed added count shows a partial badge");
assertEqual(partialAddedDisplay.isAvailable, true, "confirmed added count remains visible");

const repeatedReopenExplanation = "Ticket LHPM-1 was counted 2 times because it was reopened 2 times.";
const repeatedReopenDisplay = getReleaseMetricDisplay(
  metricsResponse({
    metrics: { ...metricsResponse().metrics, reopen_rate_pct: 200 },
    metric_availability: {
      ...metricsResponse().metric_availability!,
      metrics: {
        reopen_rate_pct: {
          status: "COMPUTED",
          available: true,
          reason: null,
          explanations: [repeatedReopenExplanation],
          missing_issue_keys: [],
          depends_on: ["ticket_count", "completed_tickets", "history_changelog", "release_assignment"],
        },
      },
    },
  }),
  "reopen_rate_pct"
);
assertEqual(repeatedReopenDisplay.isAvailable, true, "reopen values above 100 remain available");
assertEqual(
  repeatedReopenDisplay.explanations[0],
  repeatedReopenExplanation,
  "release display exposes repeated-reopen evidence"
);

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
      confidence_score: [{ snapshot_at: "2026-06-01T10:00:00Z", value: 88, ruleset_version: 1, version_boundary: false }],
      },
    }),
    "confidence_score",
    "No confidence history available yet."
  ),
  "No confidence history available yet.",
  "computed confidence chart keeps default empty copy"
);
