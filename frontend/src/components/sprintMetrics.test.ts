import type { DeliveryConfidenceDetail, SprintMetricValues } from "../api/types";
import {
  buildPredictabilityDisplayModel,
  buildScopeCreepDisplayModel,
  buildSprintWorkStateDisplayModel,
  buildVelocityHealthDisplayModel,
  buildWorkDistributionDisplayModel,
  calculateDelta,
  classifyWorkDistribution,
  formatDelta,
  generateFocusAreas,
  getGroupHealth,
  getGroupSummary,
  getMetricStatus,
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
    initial_commitment_count: 13,
    committed_effective_points: 60,
    completed_effective_points: 14,
    remaining_effective_points: 46,
    completed_scope_pct: 23.33,
    time_elapsed_pct: 41,
    historical_velocity: 55.67,
    baseline_sprint_count: 4,
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
  ["60% of active work", "Top 3 assignees", "Unassigned: 60%", "Mira: 40%"],
  "work distribution includes top three assignee detail"
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
