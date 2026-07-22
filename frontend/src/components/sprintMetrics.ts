import type {
  DeliveryConfidenceDetail,
  DeliveryConfidenceStatus,
  SprintMetricValues,
  SprintMetricsResponse,
  WorkloadDistributionDetail,
  WorkloadRiskBand,
} from "../api/types";
import type { MetricImpact, MetricStatus } from "./MetricCards";

export type MetricGroup = "delivery" | "quality" | "flow" | "risk" | "snapshot";

export interface MetricEvaluation {
  key: string;
  label: string;
  group: MetricGroup;
  status: MetricStatus;
  value: number | null;
  formattedValue: string;
  focusMessage: string;
}

export interface ScopeCreepDisplayModel {
  value: string;
  status: MetricStatus;
  comparison: string;
  impact: MetricImpact;
  details: string[];
  issueKeys: string[];
  hiddenIssueCount: number;
}

export interface VelocityHealthDisplayModel {
  value: string;
  status: MetricStatus;
  comparison: string;
  impact: MetricImpact;
  details: string[];
}

export interface PredictabilityDisplayModel {
  value: string;
  status: MetricStatus;
  comparison: string;
  impact: MetricImpact;
  details: string[];
}

export interface WorkDistributionDisplayModel {
  title: string;
  value: string;
  status: MetricStatus;
  comparison: string;
  impact: MetricImpact;
  details: string[];
  badge: string | null;
  badgeTitle: string | null;
}

export interface SprintWorkStateDisplayModel {
  value: string;
  status: MetricStatus;
  comparison: string;
  impact: MetricImpact;
  details: string[];
  badge: string | null;
  badgeTitle: string | null;
}

export interface SprintCommitmentReliabilityRow {
  sprint_id: string;
  name: string;
  committed_story_points: number;
  completed_story_points: number;
  is_not_closed: boolean;
}

export interface SprintStoryPointUiVisibility {
  hasStoryPointMetrics: boolean;
  showStoryPointUnavailableMessage: boolean;
  showStoryPointChartEmptyState: boolean;
  showPointValues: boolean;
  showRiskDrivers: boolean;
  showVelocityHealth: boolean;
  showTeamPredictability: boolean;
  showDeliveryConfidenceBreakdown: boolean;
  showDeliveryConfidenceTrend: boolean;
  showCommitmentReliability: boolean;
  showTicketCountMetrics: boolean;
}

export const sprintNoTicketsReason = "No tickets are available for this scope.";
export const sprintNoStoryPointsReason = "Delivery confidence requires at least 50% of sprint tickets to have valid story points.";
export const sprintNoChangelogReason = "No Jira changelog history is available for this scope.";

function storyPointCoverageReason(minimumCoveragePct: number) {
  return `Delivery confidence requires at least ${minimumCoveragePct}% of sprint tickets to have valid story points.`;
}

export function getSprintStoryPointCoverageStatus(
  metrics: SprintMetricsResponse | null | undefined,
  minimumCoveragePct = 50,
): DeliveryConfidenceStatus {
  const coverage = metrics?.story_point_coverage;
  if (!metrics?.is_computed || !coverage || coverage.total_ticket_count === 0) {
    return "NOT_COMPUTED";
  }
  if (coverage.coverage_pct < minimumCoveragePct) {
    return "INCONCLUSIVE";
  }
  return coverage.coverage_pct < 100 ? "PARTIAL" : "COMPUTED";
}

export function hasSprintStoryPoints(
  metrics: SprintMetricsResponse | null | undefined,
  minimumCoveragePct = 50,
) {
  const coverageStatus = getSprintStoryPointCoverageStatus(metrics, minimumCoveragePct);
  return coverageStatus === "PARTIAL" || coverageStatus === "COMPUTED";
}

export function hasSprintDeliveryConfidence(metrics: SprintMetricsResponse | null | undefined) {
  return Boolean(
    metrics?.delivery_confidence
    && (metrics.delivery_confidence_status === "PARTIAL" || metrics.delivery_confidence_status === "COMPUTED")
  );
}

export function getSprintStoryPointUnavailableReason(
  metrics: SprintMetricsResponse | null | undefined,
  minimumCoveragePct = 50,
) {
  const deliveryConfidenceAvailability = metrics?.metric_availability?.metrics.delivery_confidence_score;
  if (deliveryConfidenceAvailability && !deliveryConfidenceAvailability.available && deliveryConfidenceAvailability.reason) {
    return deliveryConfidenceAvailability.reason;
  }
  if (metrics?.unavailable_reason) {
    return metrics.unavailable_reason;
  }
  return storyPointCoverageReason(minimumCoveragePct);
}

export function getSprintMetricAvailabilityReason(
  metrics: SprintMetricsResponse | null | undefined,
  metricName: keyof SprintMetricValues
) {
  const availability = metrics?.metric_availability?.metrics[metricName];
  return availability && !availability.available ? availability.reason : null;
}

export function getSprintMetricExplanations(
  metrics: SprintMetricsResponse | null | undefined,
  metricName: keyof SprintMetricValues
) {
  return metrics?.metric_availability?.metrics[metricName]?.explanations ?? [];
}

export function getSprintMetricUnavailableBadge(reason: string | null | undefined) {
  if (!reason) {
    return null;
  }
  if (reason === sprintNoTicketsReason) {
    return "No tickets";
  }
  if (reason === sprintNoStoryPointsReason || reason.startsWith("Delivery confidence requires at least ")) {
    return "No story points";
  }
  if (reason === sprintNoChangelogReason) {
    return "No history";
  }
  return "Unavailable";
}

export function getSprintMetricDisplay(
  metrics: SprintMetricsResponse | null | undefined,
  metricName: keyof SprintMetricValues
) {
  const availability = metrics?.metric_availability?.metrics[metricName];
  const explanations = availability?.explanations ?? [];
  const missingIssueKeys = availability?.missing_issue_keys ?? [];
  if (availability?.status === "PARTIAL" && availability.available) {
    return {
      value: null,
      badge: "Partial",
      reason: explanations[0] ?? availability.reason,
      explanations,
      missingIssueKeys,
      isAvailable: true,
    };
  }
  if (availability && !availability.available) {
    return {
      value: "N/A",
      badge: availability.status === "PARTIAL"
        ? "Partial"
        : availability.status === "NOT_APPLICABLE"
          ? "Not applicable"
          : getSprintMetricUnavailableBadge(availability.reason),
      reason: explanations[0] ?? availability.reason,
      explanations,
      missingIssueKeys,
      isAvailable: false,
    };
  }
  return {
    value: null,
    badge: null,
    reason: null,
    explanations,
    missingIssueKeys,
    isAvailable: true,
  };
}

export function buildSprintStoryPointUiVisibility(
  metrics: SprintMetricsResponse | null | undefined,
  minimumCoveragePct = 50,
): SprintStoryPointUiVisibility {
  const hasStoryPointMetrics = hasSprintStoryPoints(metrics, minimumCoveragePct);
  const hasDeliveryConfidence = hasSprintDeliveryConfidence(metrics);
  const hasComputedMetrics = metrics?.is_computed === true;
  const hasCoverageExplanation = (metrics?.delivery_confidence_explanations.length ?? 0) > 0;

  return {
    hasStoryPointMetrics,
    showStoryPointUnavailableMessage: hasComputedMetrics && hasCoverageExplanation,
    showStoryPointChartEmptyState: hasComputedMetrics && !hasStoryPointMetrics,
    showPointValues: hasDeliveryConfidence,
    showRiskDrivers: hasDeliveryConfidence,
    showVelocityHealth: hasDeliveryConfidence,
    showTeamPredictability: hasStoryPointMetrics,
    showDeliveryConfidenceBreakdown: hasDeliveryConfidence,
    showDeliveryConfidenceTrend: hasStoryPointMetrics,
    showCommitmentReliability: hasStoryPointMetrics,
    showTicketCountMetrics: hasComputedMetrics,
  };
}

export function formatPercent(value: number) {
  return `${value.toFixed(2)}%`;
}

export function formatWholePercent(value: number) {
  return `${Math.round(value)}%`;
}

export function formatPoints(value: number) {
  return `${Number(value.toFixed(2))} SP`;
}

export function getMetricStatus(metricName: keyof SprintMetricValues, value: number | null): MetricStatus {
  if (value === null) {
    return "neutral";
  }
  if (metricName === "open_blockers") {
    return value > 0 ? "critical" : "good";
  }
  if (metricName === "open_high_severity_bugs") {
    if (value > 1) {
      return "critical";
    }
    return value > 0 ? "warning" : "good";
  }
  if (metricName === "bugs_created_during_sprint") {
    return value > 0 ? "warning" : "good";
  }
  if (metricName === "completed_scope_pct") {
    if (value >= 80) {
      return "good";
    }
    return value >= 50 ? "warning" : "critical";
  }
  if (metricName === "rollover_count") {
    return value > 0 ? "critical" : "good";
  }
  if (metricName === "median_cycle_time_days") {
    return value > 7 ? "warning" : "good";
  }
  if (metricName === "reopen_rate_pct") {
    if (value > 15) {
      return "critical";
    }
    return value > 10 ? "warning" : "good";
  }
  return "neutral";
}

export function getRatioStatus(value: number | null, healthy = 85, watch = 60): MetricStatus {
  if (value === null) {
    return "neutral";
  }
  if (value >= healthy) {
    return "good";
  }
  return value >= watch ? "warning" : "critical";
}

export function calculateDelta(current: number | null, previous: number | null) {
  if (current === null || previous === null) {
    return null;
  }
  return current - previous;
}

export function formatDelta(delta: number | null, formatter: (value: number) => string) {
  if (delta === null) {
    return null;
  }
  if (delta === 0) {
    return "Unchanged since last snapshot";
  }
  return `${delta > 0 ? "+" : "-"}${formatter(Math.abs(delta))} since last snapshot`;
}

export function getGroupHealth(evaluations: MetricEvaluation[], group: MetricGroup): MetricStatus {
  const groupItems = evaluations.filter((item) => item.group === group);
  if (groupItems.some((item) => item.status === "critical")) {
    return "critical";
  }
  if (groupItems.some((item) => item.status === "warning")) {
    return "warning";
  }
  if (groupItems.some((item) => item.status === "good")) {
    return "good";
  }
  return "neutral";
}

export function getGroupSummary(group: MetricGroup, evaluations: MetricEvaluation[]) {
  const groupItems = evaluations.filter((item) => item.group === group);
  const critical = groupItems.filter((item) => item.status === "critical");
  const warning = groupItems.filter((item) => item.status === "warning");

  if (group === "delivery") {
    if (critical.some((item) => item.key === "completed_scope_pct") && critical.some((item) => item.key === "scope_creep")) {
      return "Delivery is at risk due to low completion and high scope creep.";
    }
    if (critical.length > 0 || warning.length > 0) {
      return `Delivery needs attention: ${[...critical, ...warning].map((item) => item.label.toLowerCase()).join(", ")}.`;
    }
    return "Delivery metrics are tracking within expected ranges.";
  }

  if (group === "quality") {
    const highSeverity = [...critical, ...warning].find((item) => item.key === "open_high_severity_bugs");
    if (highSeverity) {
      return "Quality is stable, but high-severity bugs require attention.";
    }
    if (critical.length > 0 || warning.length > 0) {
      return `Quality needs attention: ${[...critical, ...warning].map((item) => item.label.toLowerCase()).join(", ")}.`;
    }
    return "Quality metrics are stable.";
  }

  if (group === "flow") {
    if (critical.length > 0 || warning.length > 0) {
      return `Flow needs attention: ${[...critical, ...warning].map((item) => item.label.toLowerCase()).join(", ")}.`;
    }
    return "Flow metrics are stable.";
  }

  if (group === "risk") {
    if (critical.length > 0 || warning.length > 0) {
      return `Risk needs attention: ${[...critical, ...warning].map((item) => item.label.toLowerCase()).join(", ")}.`;
    }
    return "No major sprint risk indicators are active.";
  }

  return "Sprint work state is summarized from the current sprint snapshot.";
}

export function generateFocusAreas(evaluations: MetricEvaluation[]) {
  const actionable = evaluations
    .map((item, index) => ({ item, index }))
    .filter(({ item }) => item.status === "critical" || item.status === "warning")
    .sort((left, right) => {
      const severityScore = (status: MetricStatus) => (status === "critical" ? 0 : 1);
      return severityScore(left.item.status) - severityScore(right.item.status) || left.index - right.index;
    });

  if (actionable.length === 0) {
    return ["No major metric risks detected."];
  }

  return actionable.slice(0, 3).map(({ item }) => item.focusMessage);
}

export function buildScopeCreepDisplayModel(confidence: DeliveryConfidenceDetail): ScopeCreepDisplayModel {
  const index = confidence.inputs.scope_stability_index;
  const creepPct = index === null ? null : Number((index * 100).toFixed(2));
  const status: MetricStatus = creepPct === null ? "neutral" : creepPct > 20 ? "critical" : creepPct > 10 ? "warning" : "good";
  const added = confidence.inputs.scope_added_count;
  const removed = confidence.inputs.scope_removed_count;
  const netChange = added - removed;
  const issueKeys = confidence.inputs.scope_change_issue_keys ?? [];

  return {
    value: creepPct === null ? "N/A" : formatPercent(creepPct),
    status,
    comparison:
      confidence.inputs.scope_change_count === 0
        ? "No scope changes after sprint start"
        : `${confidence.inputs.scope_change_count} scope changes after sprint start`,
    impact: confidence.inputs.scope_change_count === 0 ? "positive" : "negative",
    details: [
      `${added} added`,
      `${removed} removed`,
      `Net ${netChange >= 0 ? "+" : ""}${netChange}`,
    ],
    issueKeys: issueKeys.slice(0, 5),
    hiddenIssueCount: Math.max(0, issueKeys.length - 5),
  };
}

export function buildVelocityHealthDisplayModel(confidence: DeliveryConfidenceDetail): VelocityHealthDisplayModel {
  const completed = confidence.inputs.completed_effective_points;
  const average = confidence.inputs.historical_velocity;
  const remainingCapacity = confidence.inputs.remaining_capacity_points;
  const projected = remainingCapacity === null ? completed : completed + Math.max(remainingCapacity, 0);
  const pct = average && average > 0 ? Number(((completed / average) * 100).toFixed(0)) : null;
  const status = getRatioStatus(pct, 85, 60);

  if (average === null || average === 0) {
    return {
      value: "Not enough data yet",
      status: "neutral",
      comparison: "Requires closed sprint velocity history.",
      impact: "unknown",
      details: [`Projected completion: ${formatPoints(projected)}`],
    };
  }

  return {
    value: pct === null ? "N/A" : `${pct}%`,
    status,
    comparison: `Velocity health: ${pct}%`,
    impact: status === "good" ? "positive" : "negative",
    details: [
      `Projected completion: ${formatPoints(projected)}`,
      `Historical average: ${formatPoints(average)}`,
    ],
  };
}

export function buildPredictabilityDisplayModel(
  rows: SprintCommitmentReliabilityRow[]
): PredictabilityDisplayModel {
  const closedRows = rows.filter((row) => !row.is_not_closed && row.committed_story_points > 0);
  if (closedRows.length < 2) {
    return {
      value: "Not enough data yet",
      status: "neutral",
      comparison: "Requires at least 2 closed sprints.",
      impact: "unknown",
      details: [],
    };
  }

  const ratios = closedRows.map((row) => row.completed_story_points / row.committed_story_points);
  const pct = Number(((ratios.reduce((sum, value) => sum + value, 0) / ratios.length) * 100).toFixed(0));
  const status = getRatioStatus(pct, 90, 75);

  return {
    value: `${pct}%`,
    status,
    comparison: `Last ${closedRows.length} sprints: completed vs committed`,
    impact: status === "good" ? "positive" : status === "warning" ? "neutral" : "negative",
    details: closedRows.map(
      (row) => `${row.name}: ${Number(row.completed_story_points.toFixed(2))}/${Number(row.committed_story_points.toFixed(2))} SP`
    ),
  };
}

function isDoneStatus(status: string | null) {
  const normalized = (status ?? "").trim().toLowerCase();
  return normalized === "done" || normalized === "closed" || normalized === "resolved";
}

export function classifyWorkDistribution(riskBand: WorkloadRiskBand | null): MetricStatus {
  if (riskBand === "healthy") {
    return "good";
  }
  if (riskBand === "watch") {
    return "warning";
  }
  return riskBand === "critical" ? "critical" : "neutral";
}

export function buildWorkDistributionDisplayModel(
  workload: WorkloadDistributionDetail | null | undefined
): WorkDistributionDisplayModel {
  if (!workload) {
    return {
      title: "Workload concentration",
      value: "Not computed yet",
      status: "neutral",
      comparison: "No authoritative workload snapshot is available.",
      impact: "unknown",
      details: [],
      badge: null,
      badgeTitle: null,
    };
  }

  const evidence = workload.evidence;
  const explanation = workload.explanations[0] ?? null;
  const evidenceDetails = [
    ...(evidence.missing_status_issue_keys.length > 0
      ? [`Tickets missing status: ${evidence.missing_status_issue_keys.join(", ")}`]
      : []),
    ...(evidence.excluded_active_issue_keys.length > 0
      ? [`Excluded active tickets: ${evidence.excluded_active_issue_keys.join(", ")}`]
      : []),
    ...(evidence.assignee_identity_fallback_issue_keys.length > 0
      ? [`Display-name identity fallback: ${evidence.assignee_identity_fallback_issue_keys.join(", ")}`]
      : []),
  ];

  if (workload.status === "INCONCLUSIVE") {
    return {
      title: "Workload concentration",
      value: "Inconclusive",
      status: "neutral",
      comparison: explanation ?? "The backend could not determine active workload concentration.",
      impact: "unknown",
      details: [...workload.explanations.slice(1), ...evidenceDetails],
      badge: "Inconclusive",
      badgeTitle: workload.explanations.join(" ") || null,
    };
  }

  if (workload.status === "NOT_APPLICABLE") {
    return {
      title: "Workload concentration",
      value: "Not applicable",
      status: "neutral",
      comparison: explanation ?? "The sprint has no active tickets.",
      impact: "unknown",
      details: [...workload.explanations.slice(1), ...evidenceDetails],
      badge: "Not applicable",
      badgeTitle: explanation,
    };
  }

  if (workload.status === "NOT_COMPUTED" || workload.percentage === null) {
    return {
      title: "Workload concentration",
      value: "Unavailable",
      status: "neutral",
      comparison: explanation ?? "The backend did not produce a workload concentration value.",
      impact: "unknown",
      details: [...workload.explanations.slice(1), ...evidenceDetails],
      badge: "Unavailable",
      badgeTitle: explanation,
    };
  }

  const status = classifyWorkDistribution(evidence.risk_band);
  const topAssignee = evidence.top_assignee;
  const assigneeRows = evidence.assignee_totals.map((item) => {
    const issueEvidence = item.issue_keys.length > 0 ? ` — ${item.issue_keys.join(", ")}` : "";
    return `${item.assignee}: ${formatPoints(item.story_points)}${issueEvidence}`;
  });

  return {
    title: "Workload concentration",
    value: formatPercent(workload.percentage),
    status,
    comparison: topAssignee
      ? `Top assignee: ${topAssignee.assignee}`
      : "Top-assignee evidence is unavailable.",
    impact: status === "good" ? "positive" : status === "neutral" ? "unknown" : "negative",
    details: [
      ...workload.explanations,
      ...(evidence.risk_band ? [`Risk band: ${evidence.risk_band}`] : []),
      ...(topAssignee ? [`Top-assignee points: ${formatPoints(topAssignee.story_points)}`] : []),
      ...(evidence.total_active_points !== null
        ? [`Total included active points: ${formatPoints(evidence.total_active_points)}`]
        : []),
      ...(evidence.included_active_issue_keys.length > 0
        ? [`Included active tickets: ${evidence.included_active_issue_keys.join(", ")}`]
        : []),
      ...(assigneeRows.length > 0 ? ["Assignee totals", ...assigneeRows] : []),
      ...evidenceDetails,
    ],
    badge: workload.status === "PARTIAL" ? "Partial" : null,
    badgeTitle: workload.status === "PARTIAL"
      ? workload.explanations.join(" ") || "Computed from partial workload evidence."
      : null,
  };
}

export function buildSprintWorkStateDisplayModel(
  response: SprintMetricsResponse,
  issues: Array<{ status: string | null }>
): SprintWorkStateDisplayModel {
  const metrics = response.metrics;
  const currentScope = metrics.committed_scope;
  const inProgress = metrics.in_progress_count;
  const notStarted = metrics.not_started_count;
  const rollover = metrics.rollover_count;
  const doneCount = issues.filter((issue) => isDoneStatus(issue.status)).length;
  const blocked = metrics.open_blockers;
  const availability = response.metric_availability?.metrics ?? {};
  const relevantAvailability = [
    availability.in_progress_count,
    availability.not_started_count,
    availability.rollover_count,
  ].filter((item) => item !== undefined);
  const partialItems = relevantAvailability.filter((item) => item.status === "PARTIAL");
  const partialExplanations = Array.from(
    new Set(partialItems.flatMap((item) => item.explanations))
  );
  const missingStatusIssueKeys = Array.from(
    new Set(partialItems.flatMap((item) => item.missing_issue_keys))
  ).sort();
  const currentScopeAvailability = availability.committed_scope;
  const rolloverAvailability = availability.rollover_count;
  const status: MetricStatus = currentScope === null
    ? "neutral"
    : blocked !== null && blocked > 0
      ? "critical"
      : rollover !== null && rollover > 0
        ? "warning"
        : "good";
  const badge = partialItems.length > 0
    ? "Partial"
    : currentScopeAvailability?.available === false
      ? getSprintMetricUnavailableBadge(currentScopeAvailability.reason)
      : null;
  const badgeTitle = partialExplanations[0]
    ?? (currentScopeAvailability?.available === false ? currentScopeAvailability.reason : null);
  const unfinishedValue = rolloverAvailability?.status === "NOT_APPLICABLE"
    ? "N/A (not applicable)"
    : (rollover ?? "N/A");

  return {
    value: currentScope === null ? "Not enough data yet" : `${currentScope} in current scope`,
    status,
    comparison: currentScope === null
      ? "Requires computed sprint metrics."
      : `${doneCount} ${partialItems.length > 0 ? "known done" : "done"}`,
    impact: status === "neutral" ? "unknown" : status === "good" ? "positive" : "negative",
    details: [
      `Current scope: ${currentScope ?? "N/A"}`,
      `In progress: ${inProgress ?? "N/A"}`,
      `Not started: ${notStarted ?? "N/A"}`,
      `Done: ${doneCount}`,
      `Unfinished closed-sprint scope: ${unfinishedValue}`,
      ...partialExplanations,
      ...(missingStatusIssueKeys.length > 0
        ? [`Missing status: ${missingStatusIssueKeys.join(", ")}`]
        : []),
    ],
    badge,
    badgeTitle,
  };
}
