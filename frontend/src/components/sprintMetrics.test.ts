import type {
  DeliveryConfidenceDetail,
  MetricAvailabilityItem,
  SprintMetricValues,
  SprintMetricsResponse,
  WorkloadDistributionDetail,
  WorkloadDistributionEvidence,
} from "../api/types";
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
  getSprintMetricExplanations,
  getSprintMetricAvailabilityReason,
  getSprintMetricDisplay,
  getSprintMetricUnavailableBadge,
  getSprintStoryPointCoverageStatus,
  getSprintStoryPointUnavailableReason,
  hasSprintDeliveryConfidence,
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

function availabilityItem(
  overrides: Partial<MetricAvailabilityItem> = {}
): MetricAvailabilityItem {
  return {
    status: "COMPUTED",
    available: true,
    reason: null,
    explanations: [],
    missing_issue_keys: [],
    depends_on: ["ticket_count", "ticket_status", "sprint_assignment"],
    ...overrides,
  };
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
  workload_concentration_pct: null,
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
    workload_distribution: null,
    confidence_breakdown: null,
    biggest_driver: null,
    recommendations: [],
    is_computed: true,
    snapshot_age_hours: 1,
  };
}

type WorkloadDistributionOverrides = Partial<Omit<WorkloadDistributionDetail, "evidence">> & {
  evidence?: Partial<WorkloadDistributionEvidence>;
};

function workloadDistribution(
  overrides: WorkloadDistributionOverrides = {}
): WorkloadDistributionDetail {
  const status = overrides.status ?? "COMPUTED";
  const percentage = overrides.percentage === undefined ? 60 : overrides.percentage;
  const explanations = overrides.explanations ?? [];
  const topAssignee = {
    assignee_key: "jira:ava",
    assignee: "Ava",
    story_points: 6,
    issue_keys: ["LHPM-1"],
  };
  return {
    status,
    percentage,
    explanations,
    evidence: {
      calculation_status: status,
      workload_concentration_pct: percentage,
      current_scope_issue_keys: ["LHPM-1", "LHPM-2"],
      active_issue_keys: ["LHPM-1", "LHPM-2"],
      included_active_issue_keys: ["LHPM-1", "LHPM-2"],
      excluded_active_issue_keys: [],
      missing_status_issue_keys: [],
      assignee_identity_fallback_issue_keys: [],
      assignee_totals: [
        topAssignee,
        {
          assignee_key: "jira:noah",
          assignee: "Noah",
          story_points: 4,
          issue_keys: ["LHPM-2"],
        },
      ],
      total_active_points: 10,
      top_assignee: topAssignee,
      risk_band: "critical",
      story_point_coverage: {
        total_ticket_count: 2,
        pointed_ticket_count: 2,
        unpointed_ticket_count: 0,
        coverage_pct: 100,
        unpointed_issue_keys: [],
      },
      ...overrides.evidence,
    },
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
assertEqual(classifyWorkDistribution("healthy"), "good", "stored healthy band maps to good");
assertEqual(classifyWorkDistribution("watch"), "warning", "stored watch band maps to warning");
assertEqual(classifyWorkDistribution("critical"), "critical", "stored critical band maps to critical");
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

const prerequisiteInconclusiveResponse: SprintMetricsResponse = {
  ...sprintMetricsResponse(true),
  metrics: {
    ...metrics,
    delivery_confidence_score: null,
  },
  delivery_confidence_status: "INCONCLUSIVE",
  delivery_confidence_explanations: [
    "Delivery confidence is inconclusive because sprint duration is missing its end time.",
  ],
  delivery_confidence: null,
  confidence_breakdown: null,
  biggest_driver: null,
  metric_availability: {
    ...sprintMetricsResponse(true).metric_availability!,
    metrics: {
      delivery_confidence_score: availabilityItem({
        status: "NOT_COMPUTED",
        available: false,
        reason: "Delivery confidence is inconclusive because sprint duration is missing its end time.",
        explanations: [
          "Delivery confidence is inconclusive because sprint duration is missing its end time.",
        ],
        missing_issue_keys: ["LHPM-3"],
      }),
    },
  },
};
const prerequisiteInconclusiveUi = buildSprintStoryPointUiVisibility(
  prerequisiteInconclusiveResponse
);
assertEqual(
  getSprintStoryPointCoverageStatus(prerequisiteInconclusiveResponse),
  "COMPUTED",
  "complete point coverage remains computed when confidence prerequisites are missing"
);
assertEqual(
  hasSprintStoryPoints(prerequisiteInconclusiveResponse),
  true,
  "confidence prerequisites do not hide independently available point features"
);
assertEqual(
  hasSprintDeliveryConfidence(prerequisiteInconclusiveResponse),
  false,
  "inconclusive prerequisites withhold current delivery confidence"
);
assertEqual(
  prerequisiteInconclusiveUi.showPointValues,
  false,
  "inconclusive confidence does not render score component inputs"
);
assertEqual(
  prerequisiteInconclusiveUi.showDeliveryConfidenceBreakdown,
  false,
  "inconclusive confidence does not render a component breakdown"
);
assertEqual(
  prerequisiteInconclusiveUi.showTeamPredictability,
  true,
  "complete point coverage preserves independent predictability features"
);
assertEqual(
  prerequisiteInconclusiveUi.showCommitmentReliability,
  true,
  "complete point coverage preserves commitment reliability"
);
assertEqual(
  prerequisiteInconclusiveUi.showDeliveryConfidenceTrend,
  true,
  "historical confidence remains eligible to render with a null current point"
);
assertEqual(
  prerequisiteInconclusiveUi.showStoryPointChartEmptyState,
  false,
  "missing confidence prerequisites are not mislabeled as missing story points"
);
const partialCoverageInconclusiveResponse: SprintMetricsResponse = {
  ...prerequisiteInconclusiveResponse,
  story_point_coverage: {
    total_ticket_count: 2,
    pointed_ticket_count: 1,
    unpointed_ticket_count: 1,
    coverage_pct: 50,
    unpointed_issue_keys: ["LHPM-2"],
  },
};
assertEqual(
  getSprintStoryPointCoverageStatus(partialCoverageInconclusiveResponse),
  "PARTIAL",
  "50 percent coverage remains partial even when another prerequisite is inconclusive"
);
assertEqual(
  getSprintMetricAvailabilityReason(
    {
      ...sprintMetricsResponse(true),
      metric_availability: {
        ...sprintMetricsResponse(true).metric_availability!,
        metrics: {
          median_cycle_time_days: {
            status: "NOT_COMPUTED",
            available: false,
            reason: "No Jira changelog history is available for this scope.",
            explanations: ["No Jira changelog history is available for this scope."],
            missing_issue_keys: [],
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

const repeatedReopenExplanation = "Ticket LHPM-7 was counted 3 times because it was reopened 3 times.";
assertDeepEqual(
  getSprintMetricExplanations(
    {
      ...sprintMetricsResponse(true),
      metric_availability: {
        ...sprintMetricsResponse(true).metric_availability!,
        metrics: {
          reopen_rate_pct: {
            status: "COMPUTED",
            available: true,
            reason: null,
            explanations: [repeatedReopenExplanation],
            missing_issue_keys: [],
            depends_on: ["ticket_count", "completed_tickets", "history_changelog", "sprint_assignment"],
          },
        },
      },
    },
    "reopen_rate_pct"
  ),
  [repeatedReopenExplanation],
  "sprint display exposes repeated-reopen evidence"
);
assertEqual(getMetricStatus("reopen_rate_pct", 200), "critical", "reopen values above 100 remain valid risk inputs");

const emptyScopeReason = "No tickets are available for this scope.";
const emptyScopeResponse: SprintMetricsResponse = {
  ...sprintMetricsResponse(true),
  metrics: {
    ...metrics,
    committed_scope: null,
    completed_scope_pct: null,
  },
  metric_availability: {
    ...sprintMetricsResponse(true).metric_availability!,
    metrics: {
      committed_scope: {
        status: "NOT_COMPUTED",
        available: false,
        reason: emptyScopeReason,
        explanations: [emptyScopeReason],
        missing_issue_keys: [],
        depends_on: ["ticket_count", "sprint_assignment"],
      },
      completed_scope_pct: {
        status: "NOT_COMPUTED",
        available: false,
        reason: emptyScopeReason,
        explanations: [emptyScopeReason],
        missing_issue_keys: [],
        depends_on: ["ticket_count", "ticket_status", "sprint_assignment"],
      },
    },
  },
};
const emptyCurrentScopeDisplay = getSprintMetricDisplay(emptyScopeResponse, "committed_scope");
assertEqual(emptyCurrentScopeDisplay.value, "N/A", "empty current scope displays N/A");
assertEqual(emptyCurrentScopeDisplay.badge, "No tickets", "empty current scope explains that no tickets exist");
assertEqual(emptyCurrentScopeDisplay.isAvailable, false, "empty current scope is unavailable");

const missingStatusReason = "Completed scope is unavailable because 1 current sprint ticket(s) have no status.";
const partialCompletionResponse: SprintMetricsResponse = {
  ...sprintMetricsResponse(true),
  metrics: {
    ...metrics,
    committed_scope: 2,
    completed_scope_pct: null,
  },
  metric_availability: {
    ...sprintMetricsResponse(true).metric_availability!,
    metrics: {
      completed_scope_pct: {
        status: "PARTIAL",
        available: false,
        reason: missingStatusReason,
        explanations: [missingStatusReason],
        missing_issue_keys: ["LHPM-2"],
        depends_on: ["ticket_count", "ticket_status", "sprint_assignment"],
      },
    },
  },
};
const partialCompletionDisplay = getSprintMetricDisplay(partialCompletionResponse, "completed_scope_pct");
assertEqual(partialCompletionDisplay.value, "N/A", "partial completed scope displays N/A");
assertEqual(partialCompletionDisplay.badge, "Partial", "partial completed scope displays a partial badge");
assertEqual(partialCompletionDisplay.reason, missingStatusReason, "partial completed scope exposes the API explanation");
assertEqual(partialCompletionDisplay.isAvailable, false, "partial completed scope remains unavailable");

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

const workDistribution = buildWorkDistributionDisplayModel(workloadDistribution());
assertEqual(workDistribution.title, "Workload concentration", "work distribution title is PM-facing");
assertEqual(workDistribution.value, "60.00%", "work distribution uses the stored backend percentage");
assertEqual(workDistribution.status, "critical", "work distribution uses the stored critical band");
assertEqual(workDistribution.comparison, "Top assignee: Ava", "work distribution names the stored top assignee");
assertDeepEqual(
  workDistribution.details,
  [
    "Risk band: critical",
    "Top-assignee points: 6 SP",
    "Total included active points: 10 SP",
    "Included active tickets: LHPM-1, LHPM-2",
    "Assignee totals",
    "Ava: 6 SP — LHPM-1",
    "Noah: 4 SP — LHPM-2",
  ],
  "work distribution displays stored point and issue evidence without recomputing shares"
);
assertEqual(workDistribution.badge, null, "computed workload does not show a partial badge");

const workloadAt35 = buildWorkDistributionDisplayModel(
  workloadDistribution({ percentage: 35, evidence: { workload_concentration_pct: 35, risk_band: "watch" } })
);
const workloadAt50 = buildWorkDistributionDisplayModel(
  workloadDistribution({ percentage: 50, evidence: { workload_concentration_pct: 50, risk_band: "watch" } })
);
const workloadAbove50 = buildWorkDistributionDisplayModel(
  workloadDistribution({ percentage: 50.01, evidence: { workload_concentration_pct: 50.01, risk_band: "critical" } })
);
assertEqual(workloadAt35.status, "warning", "stored 35% watch boundary displays warning");
assertEqual(workloadAt50.status, "warning", "stored 50% watch boundary displays warning");
assertEqual(workloadAbove50.status, "critical", "stored value above 50% displays critical");

const partialPointWorkDistribution = buildWorkDistributionDisplayModel(
  workloadDistribution({
    status: "PARTIAL",
    percentage: 75,
    explanations: [
      "Workload distribution is partial because current-sprint story-point coverage is 50.0%, below 100%.",
      "Unpointed active tickets are excluded: LHPM-2, LHPM-3.",
    ],
    evidence: {
      calculation_status: "PARTIAL",
      workload_concentration_pct: 75,
      included_active_issue_keys: ["LHPM-1", "LHPM-4"],
      excluded_active_issue_keys: ["LHPM-2", "LHPM-3"],
      assignee_identity_fallback_issue_keys: ["LHPM-1"],
      assignee_totals: [
        {
          assignee_key: "display:mira",
          assignee: "Mira",
          story_points: 3,
          issue_keys: ["LHPM-1"],
        },
        {
          assignee_key: "jira:noor",
          assignee: "Noor",
          story_points: 1,
          issue_keys: ["LHPM-4"],
        },
      ],
      total_active_points: 4,
      top_assignee: {
        assignee_key: "display:mira",
        assignee: "Mira",
        story_points: 3,
        issue_keys: ["LHPM-1"],
      },
      story_point_coverage: {
        total_ticket_count: 4,
        pointed_ticket_count: 2,
        unpointed_ticket_count: 2,
        coverage_pct: 50,
        unpointed_issue_keys: ["LHPM-2", "LHPM-3"],
      },
      risk_band: "critical",
    },
  })
);
assertEqual(partialPointWorkDistribution.value, "75.00%", "partial workload keeps the backend percentage");
assertEqual(partialPointWorkDistribution.badge, "Partial", "partial workload displays a badge");
assertDeepEqual(
  partialPointWorkDistribution.details,
  [
    "Workload distribution is partial because current-sprint story-point coverage is 50.0%, below 100%.",
    "Unpointed active tickets are excluded: LHPM-2, LHPM-3.",
    "Risk band: critical",
    "Top-assignee points: 3 SP",
    "Total included active points: 4 SP",
    "Included active tickets: LHPM-1, LHPM-4",
    "Assignee totals",
    "Mira: 3 SP — LHPM-1",
    "Noor: 1 SP — LHPM-4",
    "Excluded active tickets: LHPM-2, LHPM-3",
    "Display-name identity fallback: LHPM-1",
  ],
  "partial workload displays the stored exclusions and fallback evidence"
);

const inconclusiveWorkDistribution = buildWorkDistributionDisplayModel(
  workloadDistribution({
    status: "INCONCLUSIVE",
    percentage: null,
    explanations: ["Workload distribution requires at least 50% story-point coverage."],
    evidence: {
      calculation_status: "INCONCLUSIVE",
      workload_concentration_pct: null,
      missing_status_issue_keys: ["LHPM-4"],
      risk_band: null,
    },
  })
);
assertEqual(inconclusiveWorkDistribution.value, "Inconclusive", "work distribution stops below 50% coverage");
assertEqual(
  inconclusiveWorkDistribution.comparison,
  "Workload distribution requires at least 50% story-point coverage.",
  "work distribution displays the authoritative inconclusive explanation"
);
assertEqual(inconclusiveWorkDistribution.badge, "Inconclusive", "inconclusive workload is labeled");
assertDeepEqual(
  inconclusiveWorkDistribution.details,
  ["Tickets missing status: LHPM-4"],
  "inconclusive workload displays missing-status evidence"
);

const notApplicableWorkDistribution = buildWorkDistributionDisplayModel(
  workloadDistribution({
    status: "NOT_APPLICABLE",
    percentage: null,
    explanations: ["Workload distribution does not apply because the sprint has no active tickets."],
    evidence: {
      calculation_status: "NOT_APPLICABLE",
      workload_concentration_pct: null,
      active_issue_keys: [],
      included_active_issue_keys: [],
      assignee_totals: [],
      total_active_points: null,
      top_assignee: null,
      risk_band: null,
    },
  })
);
assertEqual(notApplicableWorkDistribution.value, "Not applicable", "no active work is not applicable");

const zeroPointWorkDistribution = buildWorkDistributionDisplayModel(
  workloadDistribution({
    status: "NOT_COMPUTED",
    percentage: null,
    explanations: ["Included active story points sum to zero."],
    evidence: {
      calculation_status: "NOT_COMPUTED",
      workload_concentration_pct: null,
      total_active_points: 0,
      top_assignee: null,
      risk_band: null,
    },
  })
);
assertEqual(zeroPointWorkDistribution.value, "Unavailable", "zero-point workload is unavailable");
assertEqual(
  zeroPointWorkDistribution.comparison,
  "Included active story points sum to zero.",
  "zero-point workload displays the stored reason"
);

const baseWorkStateResponse: SprintMetricsResponse = {
  ...sprintMetricsResponse(true),
  metrics: { ...metrics },
  metric_availability: {
    ...sprintMetricsResponse(true).metric_availability!,
    metrics: {
      committed_scope: availabilityItem({
        depends_on: ["ticket_count", "sprint_assignment"],
      }),
      in_progress_count: availabilityItem(),
      not_started_count: availabilityItem(),
      rollover_count: availabilityItem(),
    },
  },
};
const workState = buildSprintWorkStateDisplayModel(baseWorkStateResponse, [
  { status: "Done" },
  { status: "Closed" },
  { status: "In Progress" },
]);
assertDeepEqual(
  workState.details,
  [
    "Current scope: 19",
    "In progress: 7",
    "Not started: 6",
    "Done: 2",
    "Unfinished closed-sprint scope: 0",
  ],
  "work state consolidates low-value raw state cards"
);
assertEqual(workState.value, "19 in current scope", "work state uses current-scope terminology");

const notApplicableReason = "Unfinished closed-sprint scope applies only to closed sprints.";
const activeWorkStateResponse: SprintMetricsResponse = {
  ...baseWorkStateResponse,
  metrics: { ...baseWorkStateResponse.metrics, rollover_count: null },
  metric_availability: {
    ...baseWorkStateResponse.metric_availability!,
    metrics: {
      ...baseWorkStateResponse.metric_availability!.metrics,
      rollover_count: availabilityItem({
        status: "NOT_APPLICABLE",
        available: false,
        reason: notApplicableReason,
        explanations: [notApplicableReason],
      }),
    },
  },
};
const activeUnfinishedDisplay = getSprintMetricDisplay(activeWorkStateResponse, "rollover_count");
assertEqual(activeUnfinishedDisplay.value, "N/A", "active sprint unfinished scope displays N/A");
assertEqual(activeUnfinishedDisplay.badge, "Not applicable", "active sprint unfinished scope is explicitly not applicable");
const activeWorkState = buildSprintWorkStateDisplayModel(activeWorkStateResponse, [{ status: "Done" }]);
assertEqual(
  activeWorkState.details.includes("Unfinished closed-sprint scope: N/A (not applicable)"),
  true,
  "active work state does not present unavailable unfinished scope as zero"
);

const closedWorkStateResponse: SprintMetricsResponse = {
  ...baseWorkStateResponse,
  metrics: { ...baseWorkStateResponse.metrics, rollover_count: 2 },
};
const closedWorkState = buildSprintWorkStateDisplayModel(closedWorkStateResponse, [{ status: "Done" }]);
assertEqual(
  closedWorkState.details.includes("Unfinished closed-sprint scope: 2"),
  true,
  "closed work state displays the computed unfinished count"
);

const emptyWorkStateResponse: SprintMetricsResponse = {
  ...baseWorkStateResponse,
  metrics: {
    ...baseWorkStateResponse.metrics,
    committed_scope: null,
    in_progress_count: null,
    not_started_count: null,
    rollover_count: null,
  },
  metric_availability: {
    ...baseWorkStateResponse.metric_availability!,
    metrics: {
      committed_scope: availabilityItem({
        status: "NOT_COMPUTED",
        available: false,
        reason: emptyScopeReason,
        explanations: [emptyScopeReason],
        depends_on: ["ticket_count", "sprint_assignment"],
      }),
      in_progress_count: availabilityItem({
        status: "NOT_COMPUTED",
        available: false,
        reason: emptyScopeReason,
        explanations: [emptyScopeReason],
      }),
      not_started_count: availabilityItem({
        status: "NOT_COMPUTED",
        available: false,
        reason: emptyScopeReason,
        explanations: [emptyScopeReason],
      }),
      rollover_count: availabilityItem({
        status: "NOT_APPLICABLE",
        available: false,
        reason: notApplicableReason,
        explanations: [notApplicableReason],
      }),
    },
  },
};
const emptyWorkState = buildSprintWorkStateDisplayModel(emptyWorkStateResponse, []);
assertEqual(emptyWorkState.value, "Not enough data yet", "empty work state has no inferred count");
assertEqual(emptyWorkState.status, "neutral", "empty work state is not marked healthy");
assertEqual(emptyWorkState.badge, "No tickets", "empty work state explains its unavailable scope");

const workStatePartialReason =
  "In-progress count is partial because 1 current sprint ticket(s) have no status. The returned value is a confirmed minimum.";
const partialWorkStateResponse: SprintMetricsResponse = {
  ...baseWorkStateResponse,
  metrics: {
    ...baseWorkStateResponse.metrics,
    committed_scope: 3,
    in_progress_count: 1,
    not_started_count: 1,
    rollover_count: 2,
  },
  metric_availability: {
    ...baseWorkStateResponse.metric_availability!,
    metrics: {
      ...baseWorkStateResponse.metric_availability!.metrics,
      in_progress_count: availabilityItem({
        status: "PARTIAL",
        explanations: [workStatePartialReason],
        missing_issue_keys: ["LHPM-3"],
      }),
      not_started_count: availabilityItem({
        status: "PARTIAL",
        explanations: [
          "Not-started count is partial because 1 current sprint ticket(s) have no status. The returned value is a confirmed minimum.",
        ],
        missing_issue_keys: ["LHPM-3"],
      }),
      rollover_count: availabilityItem({
        status: "PARTIAL",
        explanations: [
          "Unfinished closed-sprint scope is partial because 1 current sprint ticket(s) have no status. The returned value is a confirmed minimum.",
        ],
        missing_issue_keys: ["LHPM-3"],
      }),
    },
  },
};
const partialWorkState = buildSprintWorkStateDisplayModel(partialWorkStateResponse, [
  { status: "Done" },
  { status: "In Progress" },
  { status: null },
]);
assertEqual(partialWorkState.badge, "Partial", "partial work state displays a partial badge");
assertEqual(partialWorkState.comparison, "1 known done", "partial work state labels confirmed done evidence");
assertEqual(
  partialWorkState.details.includes("Missing status: LHPM-3"),
  true,
  "partial work state exposes missing-status keys"
);
const partialInProgressDisplay = getSprintMetricDisplay(partialWorkStateResponse, "in_progress_count");
assertEqual(partialInProgressDisplay.badge, "Partial", "partial count card displays its partial badge");
assertDeepEqual(
  partialInProgressDisplay.missingIssueKeys,
  ["LHPM-3"],
  "partial count card exposes missing-status keys"
);
