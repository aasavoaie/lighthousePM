import type { DeliveryConfidenceDetail, SprintMetricValues, SprintMetricsResponse } from "../api/types";
import {
  buildPredictabilityDisplayModel,
  buildScopeCreepDisplayModel,
  buildSprintWorkStateDisplayModel,
  buildSprintStoryPointUiVisibility,
  buildVelocityHealthDisplayModel,
  buildWorkDistributionDisplayModel,
  calculateDelta,
  classifyWorkDistribution,
  formatDelta,
  generateFocusAreas,
  getGroupHealth,
  getGroupSummary,
  getMetricStatus,
  getSprintMetricAvailabilityReason,
  getSprintMetricUnavailableBadge,
  getSprintStoryPointUnavailableReason,
  hasSprintStoryPoints,
  sprintNoStoryPointsReason,
  type MetricEvaluation,
} from "./sprintMetrics";

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

const confidence: DeliveryConfidenceDetail = {
  score: 55,
  weights: {
    progress_alignment: 0.35,
    velocity_fit: 0.25,
    blocker_penalty: 0.2,
    scope_stability: 0.2,
  },
  components: {
    progress_alignment: 42,
    velocity_fit: 25,
    blocker_penalty: 100,
    scope_stability: 54,
  },
  inputs: {
    committed_issue_count: 60,
    pointed_issue_count: 60,
    initial_commitment_count: 13,
    committed_effective_points: 60,
    completed_effective_points: 14,
    remaining_effective_points: 46,
    completed_scope_pct: 23.33,
    time_elapsed_pct: 41,
    historical_velocity: 55.67,
    baseline_sprint_count: 4,
    baseline_sprints: [],
    velocity_status: "COMPUTED",
    remaining_capacity_points: 24,
    blocked_issue_ratio: 0,
    scope_change_count: 6,
    scope_added_count: 7,
    scope_removed_count: 1,
    scope_stability_index: 0.4615,
    scope_change_issue_keys: ["LHPM-1", "LHPM-2", "LHPM-3", "LHPM-4", "LHPM-5", "LHPM-6"],
    scope_added_issue_keys: [],
    scope_removed_issue_keys: [],
  },
};

const metrics: SprintMetricValues = {
  committed_scope: 19,
  completed_scope_pct: 31.58,
  open_blockers: 0,
  open_high_severity_bugs: 2,
  bugs_created_during_sprint: 0,
  in_progress_count: 7,
  not_started_count: 6,
  rollover_count: 0,
  median_cycle_time_days: 4,
  reopen_rate_pct: 0,
  delivery_confidence_score: 55,
};

function sprintMetricsResponse(hasStoryPoints: boolean): SprintMetricsResponse {
  return {
    sprint_id: "12",
    ruleset_version: 1,
    ruleset_label: "Ruleset v1",
    calculation_provenance: {},
    snapshot_at: "2026-06-01T10:00:00Z",
    computation_status: hasStoryPoints ? "PARTIAL" : "PARTIAL",
    unavailable_reason: hasStoryPoints ? "No Jira changelog history is available for this scope." : sprintNoStoryPointsReason,
    metrics,
    metric_issue_keys: {
      open_blockers: [],
      open_high_severity_bugs: [],
      bugs_created_during_sprint: [],
      bugs_created_during_sprint_missing_created_at: [],
    },
    metric_names: [],
    metric_availability: {
      context: {
        has_tickets: true,
        has_story_points: hasStoryPoints,
        has_completed_tickets: true,
        has_release_scope: false,
        has_sprint_scope: true,
        has_changelog: false,
      },
      metrics: {},
    },
    story_point_coverage: {
      total_ticket_count: 10,
      pointed_ticket_count: hasStoryPoints ? 10 : 0,
      unpointed_ticket_count: hasStoryPoints ? 0 : 10,
      coverage_pct: hasStoryPoints ? 100 : 0,
      unpointed_issue_keys: hasStoryPoints ? [] : ["LHPM-1"],
    },
    delivery_confidence_status: hasStoryPoints ? "COMPUTED" : "INCONCLUSIVE",
    bugs_created_during_sprint_status: "COMPUTED",
    delivery_confidence_explanations: hasStoryPoints ? [] : [sprintNoStoryPointsReason],
    delivery_confidence: hasStoryPoints ? confidence : null,
    confidence_breakdown: null,
    biggest_driver: null,
    recommendations: [],
    is_computed: true,
    snapshot_age_hours: 1,
  };
}

const evaluations: MetricEvaluation[] = [
  {
    key: "completed_scope_pct",
    label: "Completed scope",
    group: "delivery",
    status: "critical",
    value: 31.58,
    formattedValue: "31.58%",
    focusMessage: "Completed scope is critical at 31.58%.",
  },
  {
    key: "scope_creep",
    label: "Scope creep",
    group: "delivery",
    status: "critical",
    value: 46.15,
    formattedValue: "46.15%",
    focusMessage: "Scope creep is critical at 46.15%.",
  },
  {
    key: "velocity_health",
    label: "Velocity health",
    group: "delivery",
    status: "critical",
    value: 25,
    formattedValue: "25%",
    focusMessage: "Velocity health is only 25% of normal.",
  },
  {
    key: "open_high_severity_bugs",
    label: "High-severity bugs",
    group: "quality",
    status: "critical",
    value: 2,
    formattedValue: "2",
    focusMessage: "Open high-severity bugs require attention.",
  },
];

assertEqual(getMetricStatus("completed_scope_pct", 79.99), "warning", "completed scope below 80 is watch");
assertEqual(getMetricStatus("completed_scope_pct", 49.99), "critical", "completed scope below 50 is critical");
assertEqual(getMetricStatus("open_blockers", 1), "critical", "open blocker is critical");
assertEqual(classifyWorkDistribution(34), "good", "top load under 35 is healthy");
assertEqual(classifyWorkDistribution(35), "warning", "top load at 35 is watch");
assertEqual(classifyWorkDistribution(51), "critical", "top load over 50 is critical");
assertEqual(
  hasSprintStoryPoints(sprintMetricsResponse(true)),
  true,
  "story-point helper reads availability context"
);
assertEqual(
  hasSprintStoryPoints(sprintMetricsResponse(false)),
  false,
  "story-point helper rejects unavailable story points"
);
assertEqual(hasSprintStoryPoints(undefined), false, "story-point helper defaults missing metrics to unavailable");
const noStoryPointUi = buildSprintStoryPointUiVisibility(sprintMetricsResponse(false));
assertEqual(noStoryPointUi.showPointValues, false, "no-story-point sprint does not render point values");
assertEqual(noStoryPointUi.showRiskDrivers, false, "no-story-point sprint does not render delivery risk drivers");
assertEqual(noStoryPointUi.showVelocityHealth, false, "no-story-point sprint does not render velocity health");
assertEqual(noStoryPointUi.showTeamPredictability, false, "no-story-point sprint does not render team predictability");
assertEqual(
  noStoryPointUi.showCommitmentReliability,
  false,
  "no-story-point sprint does not render commitment reliability"
);
assertEqual(
  noStoryPointUi.showStoryPointUnavailableMessage,
  true,
  "no-story-point sprint renders a story-point unavailable state"
);
assertEqual(
  noStoryPointUi.showStoryPointChartEmptyState,
  true,
  "no-story-point sprint renders story-point chart empty states"
);
assertEqual(noStoryPointUi.showTicketCountMetrics, true, "no-story-point sprint still renders ticket-count metrics");
assertEqual(
  getSprintStoryPointUnavailableReason(sprintMetricsResponse(false)),
  sprintNoStoryPointsReason,
  "story-point unavailable reason comes from metric availability"
);
assertEqual(
  getSprintMetricUnavailableBadge(sprintNoStoryPointsReason),
  "No story points",
  "story-point unavailable reason maps to a muted badge"
);
assertEqual(
  getSprintMetricUnavailableBadge("No Jira changelog history is available for this scope."),
  "No history",
  "changelog unavailable reason maps to a muted badge"
);
const loadingStoryPointUi = buildSprintStoryPointUiVisibility(null);
assertEqual(loadingStoryPointUi.showPointValues, false, "loading sprint state does not render point values");
assertEqual(
  loadingStoryPointUi.showDeliveryConfidenceTrend,
  false,
  "loading sprint state does not render stale confidence trends"
);
assertEqual(
  loadingStoryPointUi.showStoryPointUnavailableMessage,
  false,
  "loading sprint state waits for computed availability before showing unavailable message"
);
assertEqual(
  loadingStoryPointUi.showStoryPointChartEmptyState,
  false,
  "loading sprint state does not render story-point chart empty states"
);

const pointedStoryPointUi = buildSprintStoryPointUiVisibility(sprintMetricsResponse(true));
assertEqual(pointedStoryPointUi.showPointValues, true, "pointed sprint can render point values");
assertEqual(pointedStoryPointUi.showVelocityHealth, true, "pointed sprint can render velocity health");
assertEqual(pointedStoryPointUi.showCommitmentReliability, true, "pointed sprint can render commitment reliability");
assertEqual(
  pointedStoryPointUi.showStoryPointChartEmptyState,
  false,
  "pointed sprint renders real story-point charts instead of empty states"
);
assertEqual(
  getSprintMetricAvailabilityReason(
    {
      ...sprintMetricsResponse(true),
      metric_availability: {
        ...sprintMetricsResponse(true).metric_availability!,
        metrics: {
          median_cycle_time_days: {
            available: false,
            reason: "No Jira changelog history is available for this scope.",
            depends_on: ["ticket_count", "completed_tickets", "history_changelog", "sprint_assignment"],
          },
        },
      },
    },
    "median_cycle_time_days"
  ),
  "No Jira changelog history is available for this scope.",
  "metric availability reason is returned for unavailable sprint cards"
);

assertEqual(calculateDelta(18, 10), 8, "delta subtracts previous from current");
assertEqual(formatDelta(0, (value) => `${value}%`), "Unchanged since last snapshot", "zero delta is unchanged");
assertEqual(formatDelta(8, (value) => `${value}%`), "+8% since last snapshot", "positive delta is signed");

assertEqual(getGroupHealth(evaluations, "delivery"), "critical", "group health prioritizes critical");
assertEqual(
  getGroupSummary("delivery", evaluations),
  "Delivery is at risk due to low completion and high scope creep.",
  "delivery summary combines critical completion and scope creep"
);
assertDeepEqual(
  generateFocusAreas(evaluations),
  [
    "Completed scope is critical at 31.58%.",
    "Scope creep is critical at 46.15%.",
    "Velocity health is only 25% of normal.",
  ],
  "focus areas prioritize critical metrics deterministically"
);

const scopeCreep = buildScopeCreepDisplayModel(confidence);
assertEqual(scopeCreep.value, "46.15%", "scope creep uses stability index percent");
assertDeepEqual(scopeCreep.details, ["7 added", "1 removed", "Net +6"], "scope creep includes added removed and net change");
assertEqual(scopeCreep.issueKeys.length, 5, "scope creep limits visible issue chips");
assertEqual(scopeCreep.hiddenIssueCount, 1, "scope creep reports hidden issue count");

const velocity = buildVelocityHealthDisplayModel(confidence);
assertEqual(velocity.value, "25%", "velocity health uses completed over historical average");
assertEqual(velocity.status, "critical", "velocity under 60 is critical");
assertDeepEqual(
  velocity.details,
  ["Projected completion: 38 SP", "Historical average: 55.67 SP"],
  "velocity model includes projected completion and average"
);

const predictabilityEmpty = buildPredictabilityDisplayModel([]);
assertEqual(predictabilityEmpty.value, "Not enough data yet", "predictability handles missing closed sprints");
assertEqual(predictabilityEmpty.comparison, "Requires at least 2 closed sprints.", "predictability explains missing data");

const predictability = buildPredictabilityDisplayModel([
  { sprint_id: "1", name: "Sprint 1", committed_story_points: 10, completed_story_points: 9, is_not_closed: false },
  { sprint_id: "2", name: "Sprint 2", committed_story_points: 10, completed_story_points: 10, is_not_closed: false },
]);
assertEqual(predictability.value, "95%", "predictability averages completed vs committed ratios");
assertEqual(predictability.comparison, "Last 2 sprints: completed vs committed", "predictability describes detailed baseline");

const workDistribution = buildWorkDistributionDisplayModel([
  { assignee: "Unassigned", story_points: 3, status: "In Progress" },
  { assignee: "Mira", story_points: 2, status: "To Do" },
  { assignee: "Sam", story_points: 2, status: "Done" },
]);
assertEqual(workDistribution.title, "Workload concentration", "work distribution title is PM-facing");
assertEqual(workDistribution.value, "60%", "work distribution excludes done work");
assertEqual(workDistribution.status, "critical", "work distribution flags top load over 50");
assertEqual(workDistribution.comparison, "Top assignee: Unassigned", "work distribution names top assignee");
assertDeepEqual(
  workDistribution.details,
  ["60% of pointed active work", "Top 3 assignees", "Unassigned: 60%", "Mira: 40%"],
  "work distribution includes top three assignee detail"
);

const unpointedWorkDistribution = buildWorkDistributionDisplayModel([
  { assignee: "Unassigned", story_points: null, status: "In Progress" },
  { assignee: "Mira", story_points: null, status: "To Do" },
]);
assertEqual(unpointedWorkDistribution.value, "Unavailable", "work distribution is unavailable without story points");
assertEqual(
  unpointedWorkDistribution.comparison,
  "Requires story points on active sprint work.",
  "work distribution explains missing story points"
);
assertDeepEqual(
  unpointedWorkDistribution.details,
  ["No active sprint tickets have story points."],
  "work distribution does not invent fallback points"
);

const partialPointWorkDistribution = buildWorkDistributionDisplayModel([
  { assignee: "Mira", story_points: 3, status: "In Progress" },
  { assignee: "Sam", story_points: null, status: "To Do" },
  { assignee: "Mira", story_points: null, status: "In Progress" },
  { assignee: "Noor", story_points: 1, status: "To Do" },
], "PARTIAL");
assertEqual(partialPointWorkDistribution.value, "75%", "work distribution computes from pointed active tickets");
assertDeepEqual(
  partialPointWorkDistribution.details,
  [
    "Status: PARTIAL — calculated from pointed active tickets only.",
    "2 active tickets excluded because story points are missing.",
    "75% of pointed active work",
    "Top 3 assignees",
    "Mira: 75%",
    "Noor: 25%",
  ],
  "work distribution warns when active tickets are unpointed"
);

const inconclusiveWorkDistribution = buildWorkDistributionDisplayModel([
  { assignee: "Mira", story_points: 3, status: "In Progress" },
  { assignee: "Sam", story_points: null, status: "To Do" },
], "INCONCLUSIVE");
assertEqual(inconclusiveWorkDistribution.value, "Inconclusive", "work distribution stops below 50% coverage");
assertEqual(
  inconclusiveWorkDistribution.comparison,
  "Requires story points on at least 50% of sprint tickets.",
  "work distribution explains its minimum coverage"
);

const workState = buildSprintWorkStateDisplayModel(metrics, [
  { status: "Done" },
  { status: "Closed" },
  { status: "In Progress" },
]);
assertDeepEqual(
  workState.details,
  ["Committed: 19", "In progress: 7", "Not started: 6", "Done: 2", "Rollover: 0"],
  "work state consolidates low-value raw state cards"
);
