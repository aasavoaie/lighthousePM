import type { SprintMetricsResponse } from "../api/types";
import {
  buildRiskHeatmapRows,
  buildSprintChartHistory,
  calculateMovingAverage,
  calculateReliabilityPct,
  getRiskHeatmapCellStatus,
  hasChartData,
  normalizeQualityTrend,
  normalizeScopeChange,
} from "./sprintCharts";

function assertEqual<T>(actual: T, expected: T, message: string) {
  if (actual !== expected) {
    throw new Error(`${message}: expected ${String(expected)}, received ${String(actual)}`);
  }
}

function assertDeepEqual<T>(actual: T, expected: T, message: string) {
  if (JSON.stringify(actual) !== JSON.stringify(expected)) {
    throw new Error(`${message}: expected ${JSON.stringify(expected)}, received ${JSON.stringify(actual)}`);
  }
}

function metricsResponse(overrides: Partial<SprintMetricsResponse> = {}): SprintMetricsResponse {
  return {
    sprint_id: "sprint-1",
    snapshot_at: "2026-06-01T10:00:00Z",
    computation_status: "COMPUTED",
    unavailable_reason: null,
    is_computed: true,
    snapshot_age_hours: 1,
    metric_names: [],
    metric_issue_keys: {
      open_blockers: [],
      open_high_severity_bugs: [],
      bugs_created_during_sprint: [],
      bugs_created_during_sprint_missing_created_at: [],
    },
    metric_availability: {
      context: {
        has_tickets: true,
        has_story_points: true,
        has_completed_tickets: true,
        has_release_scope: false,
        has_sprint_scope: true,
        has_changelog: true,
      },
      metrics: {},
    },
    story_point_coverage: {
      total_ticket_count: 10,
      pointed_ticket_count: 10,
      unpointed_ticket_count: 0,
      coverage_pct: 100,
      unpointed_issue_keys: [],
    },
    delivery_confidence_status: "COMPUTED",
    delivery_confidence_explanations: [],
    metrics: {
      committed_scope: 10,
      completed_scope_pct: 70,
      open_blockers: 0,
      open_high_severity_bugs: 1,
      bugs_created_during_sprint: 2,
      in_progress_count: 3,
      not_started_count: 2,
      rollover_count: 0,
      median_cycle_time_days: 6,
      reopen_rate_pct: 12,
      workload_concentration_pct: null,
      delivery_confidence_score: 72,
    },
    confidence_breakdown: null,
    biggest_driver: null,
    recommendations: [],
    delivery_confidence: {
      score: 72,
      weights: {
        progress_alignment: 0.35,
        velocity_fit: 0.25,
        blocker_penalty: 0.2,
        scope_stability: 0.2,
      },
      components: {
        progress_alignment: 70,
        velocity_fit: 65,
        blocker_penalty: 100,
        scope_stability: 75,
      },
      inputs: {
        committed_issue_count: 10,
        pointed_issue_count: 10,
        initial_commitment_count: 8,
        committed_effective_points: 20,
        completed_effective_points: 14,
        remaining_effective_points: 6,
        completed_scope_pct: 70,
        time_elapsed_pct: 60,
        historical_velocity: 18,
        baseline_sprint_count: 3,
        baseline_sprints: [],
        velocity_status: "COMPUTED",
        remaining_capacity_points: 8,
        blocked_issue_ratio: 0,
        scope_change_count: 3,
        scope_added_count: 4,
        scope_removed_count: 1,
        scope_stability_index: 0.15,
        scope_change_issue_keys: [],
        scope_added_issue_keys: [],
        scope_removed_issue_keys: [],
      },
    },
    workload_distribution: null,
    ...overrides,
    ruleset_version: overrides.ruleset_version ?? 1,
    ruleset_label: overrides.ruleset_label ?? "Ruleset v1",
    calculation_provenance: overrides.calculation_provenance ?? {},
    bugs_created_during_sprint_status: overrides.bugs_created_during_sprint_status ?? "COMPUTED",
  };
}

assertEqual(calculateReliabilityPct(20, 14), 70, "reliability divides completed by committed");
assertEqual(calculateReliabilityPct(0, 14), null, "reliability is unavailable with no commitment");
assertDeepEqual(
  calculateMovingAverage([80, 90, 100, null, 70], 3),
  [null, null, 90, null, null],
  "moving average requires a full numeric window"
);

const normalizedScope = normalizeScopeChange(metricsResponse().delivery_confidence!);
assertDeepEqual(
  normalizedScope,
  {
    scope_change_count: 3,
    scope_creep_pct: 15,
    scope_added_count: 4,
    scope_removed_count: 1,
    net_scope_change: 3,
  },
  "scope trend normalizes creep, added, removed and net change"
);
assertDeepEqual(
  normalizeQualityTrend(metricsResponse().metrics),
  {
    open_high_severity_bugs: 1,
    bugs_created_during_sprint: 2,
    reopen_rate_pct: 12,
  },
  "quality trend keeps available quality fields"
);

const history = buildSprintChartHistory([
  { sprint_id: "1", name: "Sprint 1", is_not_closed: false, metrics: metricsResponse({ sprint_id: "1" }) },
  {
    sprint_id: "2",
    name: "Sprint 2",
    is_not_closed: false,
    metrics: metricsResponse({
      sprint_id: "2",
      delivery_confidence: {
        ...metricsResponse().delivery_confidence!,
        score: 82,
        inputs: {
          ...metricsResponse().delivery_confidence!.inputs,
          committed_effective_points: 20,
          completed_effective_points: 16,
        },
      },
    }),
  },
  {
    sprint_id: "current",
    name: "Current",
    is_not_closed: true,
    metrics: metricsResponse({
      sprint_id: "current",
      delivery_confidence: {
        ...metricsResponse().delivery_confidence!,
        score: 92,
        inputs: {
          ...metricsResponse().delivery_confidence!.inputs,
          committed_effective_points: 20,
          completed_effective_points: 18,
        },
      },
    }),
  },
  {
    sprint_id: "3",
    name: "Sprint 3",
    is_not_closed: false,
    metrics: metricsResponse({
      sprint_id: "3",
      delivery_confidence: {
        ...metricsResponse().delivery_confidence!,
        score: 62,
        inputs: {
          ...metricsResponse().delivery_confidence!.inputs,
          committed_effective_points: 20,
          completed_effective_points: 20,
        },
      },
    }),
  },
]);

assertEqual(history[1].confidence_delta, 10, "confidence delta uses previous sprint");
assertEqual(history[2].predictability_avg, null, "predictability average is not shown on current sprints");
assertEqual(history[3].predictability_avg, 83.33, "predictability average uses last three closed sprint reliability values");
assertEqual(history[0].blocker_health, 100, "blocker penalty is exposed as blocker health");
assertEqual(hasChartData(history, ["median_cycle_time_days"]), true, "chart data detector finds available fields");
assertEqual(hasChartData([{ median_cycle_time_days: null }], ["median_cycle_time_days"]), false, "chart data detector rejects all-empty fields");

const crossVersionHistory = buildSprintChartHistory([
  {
    sprint_id: "legacy",
    name: "Legacy",
    is_not_closed: false,
    metrics: metricsResponse({ sprint_id: "legacy", ruleset_version: 0, ruleset_label: "Unversioned legacy result" }),
  },
  {
    sprint_id: "versioned",
    name: "Versioned",
    is_not_closed: false,
    metrics: metricsResponse({ sprint_id: "versioned", ruleset_version: 1, ruleset_label: "Ruleset v1" }),
  },
]);
assertEqual(crossVersionHistory[1].version_boundary, true, "ruleset changes create a visible chart boundary");
assertEqual(crossVersionHistory[1].confidence_delta, null, "confidence delta is unavailable across ruleset versions");

const heatmap = buildRiskHeatmapRows(history);
assertEqual(heatmap.length, 16, "heatmap produces one cell per group per sprint");
assertEqual(getRiskHeatmapCellStatus("Quality", history[0]), "watch", "quality heatmap status is deterministic");

const partialHistory = buildSprintChartHistory([
  {
    sprint_id: "partial",
    name: "Partial",
    is_not_closed: false,
    metrics: metricsResponse({
      sprint_id: "partial",
      delivery_confidence: null,
    }),
  },
]);
assertEqual(partialHistory.length, 1, "computed sprint metrics render without delivery confidence details");
assertEqual(partialHistory[0].delivery_confidence, null, "missing delivery confidence stays unavailable");
assertEqual(partialHistory[0].open_high_severity_bugs, 1, "quality data is preserved without delivery confidence");
assertEqual(partialHistory[0].quality_status, "watch", "quality heatmap can render from metric data only");

const unavailableStoryPointHistory = buildSprintChartHistory([
  {
    sprint_id: "no-points",
    name: "No points",
    is_not_closed: false,
    metrics: metricsResponse({
      sprint_id: "no-points",
      delivery_confidence_status: "INCONCLUSIVE",
      delivery_confidence_explanations: ["Insufficient story-point coverage."],
      delivery_confidence: null,
      story_point_coverage: {
        total_ticket_count: 2,
        pointed_ticket_count: 0,
        unpointed_ticket_count: 2,
        coverage_pct: 0,
        unpointed_issue_keys: ["LHPM-1", "LHPM-2"],
      },
      metric_availability: {
        context: {
          has_tickets: true,
          has_story_points: false,
          has_completed_tickets: true,
          has_release_scope: false,
          has_sprint_scope: true,
          has_changelog: true,
        },
        metrics: {},
      },
    }),
  },
]);
assertEqual(unavailableStoryPointHistory[0].delivery_confidence, null, "story-point unavailable sprint suppresses confidence");
assertEqual(unavailableStoryPointHistory[0].committed_story_points, null, "story-point unavailable sprint suppresses committed points");
assertEqual(unavailableStoryPointHistory[0].completed_story_points, null, "story-point unavailable sprint suppresses completed points");
