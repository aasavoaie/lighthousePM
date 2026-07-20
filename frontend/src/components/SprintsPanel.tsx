import { useEffect, useMemo, useState } from "react";
import { apiClient } from "../api/client";
import type {
  DeliveryConfidenceDetail,
  Sprint,
  SprintIssue,
  SprintMetricValues,
  SprintMetricsResponse,
  SnapshotBaseline,
  SnapshotChangeHistoryResponse,
  SnapshotComparisonResponse,
} from "../api/types";
import {
  MetricColors,
  MetricLineChart,
  MetricMultiBarChart,
} from "./ChartComponents";
import { BiggestDriverCard } from "./BiggestDriverCard";
import { ConfidenceBreakdownCard } from "./ConfidenceBreakdownCard";
import { RecommendationsPanel } from "./RecommendationsPanel";
import { ReportExportActions } from "./ReportExportActions";
import {
  MetricCategorySection,
  MetricStatusCard,
  type MetricImpact,
  type MetricStatus,
} from "./MetricCards";
import {
  calculateExpectedVsActualProgress,
  formatConfidencePercent,
  getBiggestDrag,
  getConfidenceStatus,
  getDeliveryConfidenceSummary,
  getRiskDrivers,
  roundPercent,
} from "./deliveryConfidence";
import {
  buildPredictabilityDisplayModel,
  buildScopeCreepDisplayModel,
  buildSprintWorkStateDisplayModel,
  buildSprintStoryPointUiVisibility,
  buildVelocityHealthDisplayModel,
  buildWorkDistributionDisplayModel,
  formatPercent,
  generateFocusAreas,
  getGroupSummary,
  getMetricStatus,
  getSprintMetricDisplay,
  getSprintStoryPointUnavailableReason,
  type MetricEvaluation,
} from "./sprintMetrics";
import {
  buildRiskHeatmapRows,
  buildSprintChartHistory,
  hasChartData,
  type RiskHeatmapCell,
  type RiskHeatmapStatus,
  type SprintChartHistoryPoint,
} from "./sprintCharts";
import { SnapshotChangePanel } from "./SnapshotChangePanel";

type SprintOption = {
  label: string;
  sprint: Sprint;
};

type SprintsPanelMode = "intelligence" | "reports";

interface SprintsPanelProps {
  refreshNonce: number;
  onSelectIssue: (issueKey: string) => void;
  mode?: SprintsPanelMode;
  projectKey?: string | null;
}

type SprintCommitmentReliabilityRow = {
  [key: string]: string | number | boolean | null | undefined;
  sprint_id: string;
  name: string;
  committed_story_points: number | null;
  completed_story_points: number | null;
  reliability_pct?: number | null;
  predictability_avg?: number | null;
  is_not_closed: boolean;
};

const sprintIssuePageSize = 100;
const committedStoryPointColor = MetricColors.committedScope;
const completedStoryPointColor = MetricColors.completedScope;

const sprintMetricLabels: Record<keyof SprintMetricValues, string> = {
  committed_scope: "Current sprint scope",
  completed_scope_pct: "Completed scope",
  open_blockers: "Open blockers",
  open_high_severity_bugs: "Open high-severity bugs",
  bugs_created_during_sprint: "Bugs created during sprint",
  in_progress_count: "In progress",
  not_started_count: "Not started",
  rollover_count: "Unfinished closed-sprint scope",
  median_cycle_time_days: "Median cycle time",
  reopen_rate_pct: "Reopen events per 100 eligible tickets",
  workload_concentration_pct: "Workload concentration",
  delivery_confidence_score: "Delivery confidence",
};

const sprintMetricInfoText: Record<keyof SprintMetricValues, string> = {
  committed_scope: "Distinct tickets currently assigned to this sprint.",
  completed_scope_pct: "Percentage of current sprint tickets whose status is done.",
  open_blockers: "Open blockers can stop delivery and should be cleared quickly.",
  open_high_severity_bugs: "Open high-severity bugs indicate quality risk inside the sprint.",
  bugs_created_during_sprint: "New bugs created during the sprint can displace planned work.",
  in_progress_count: "Current sprint tickets whose status is configured as in progress.",
  not_started_count: "Current sprint tickets with a known status outside the configured done and in-progress sets.",
  rollover_count: "Current non-done tickets in a closed sprint; this does not prove movement into another sprint.",
  median_cycle_time_days: "Typical time from active work start to done.",
  reopen_rate_pct: "Counts every done-to-not-done transition per 100 eligible tickets; one ticket can contribute more than one event.",
  workload_concentration_pct: "Authoritative share of included active sprint story points owned by the top assignee.",
  delivery_confidence_score: "Composite score from progress, velocity, blockers, and scope stability.",
};

function formatMetricValue(metricName: keyof SprintMetricValues, value: number | null) {
  if (value === null) {
    return "N/A";
  }
  if (
    metricName === "committed_scope" ||
    metricName === "open_blockers" ||
    metricName === "open_high_severity_bugs" ||
    metricName === "bugs_created_during_sprint" ||
    metricName === "in_progress_count" ||
    metricName === "not_started_count" ||
    metricName === "rollover_count"
  ) {
    return String(value);
  }
  if (
    metricName === "completed_scope_pct"
    || metricName === "reopen_rate_pct"
    || metricName === "workload_concentration_pct"
  ) {
    return `${value.toFixed(2)}%`;
  }
  return value.toFixed(2);
}

function getIssueStatusClass(issueKey: string, issuesByKey: Record<string, SprintIssue>) {
  const status = issuesByKey[issueKey]?.status?.trim().toLowerCase() ?? "";
  if (status === "blocked") {
    return "blocked";
  }
  if (status === "done" || status === "closed" || status === "resolved") {
    return "done";
  }
  if (status === "in progress" || status === "in development" || status === "in review" || status === "in testing") {
    return "in-progress";
  }
  return "todo";
}

function renderScopeIssueKeys(
  label: string,
  issueKeys: string[],
  issuesByKey: Record<string, SprintIssue>,
  onSelectIssue: (issueKey: string) => void,
  hiddenIssueCount = 0
) {
  if (issueKeys.length === 0 && hiddenIssueCount === 0) {
    return null;
  }
  return (
    <div className="scope-ticket-group">
      <span className="muted">{label}</span>
      <ul className="metric-ticket-list" aria-label={`${label} tickets`}>
        {issueKeys.map((issueKey) => (
          <li key={issueKey}>
            <button
              type="button"
              className={`link-button status-badge ${getIssueStatusClass(issueKey, issuesByKey)}`}
              onClick={() => onSelectIssue(issueKey)}
            >
              {issueKey}
            </button>
          </li>
        ))}
        {hiddenIssueCount > 0 ? (
          <li>
            <span className="status-badge overflow-badge">+{hiddenIssueCount} more</span>
          </li>
        ) : null}
      </ul>
    </div>
  );
}

function renderMetricIssueKeys(
  metricName: keyof SprintMetricValues,
  value: number | null,
  metrics: SprintMetricsResponse,
  issuesByKey: Record<string, SprintIssue>,
  onSelectIssue: (issueKey: string) => void
) {
  if (
    metricName !== "open_blockers" &&
    metricName !== "open_high_severity_bugs" &&
    metricName !== "bugs_created_during_sprint"
  ) {
    return null;
  }

  const issueKeys = metrics.metric_issue_keys[metricName] ?? [];
  if (issueKeys.length === 0) {
    return value !== null && value > 0 ? <p className="metric-ticket-empty">Recompute to populate ticket list.</p> : null;
  }

  return (
    <ul className="metric-ticket-list" aria-label={`${sprintMetricLabels[metricName]} tickets`}>
      {issueKeys.map((issueKey) => (
        <li key={issueKey}>
          <button
            type="button"
            className={`link-button status-badge ${getIssueStatusClass(issueKey, issuesByKey)}`}
            onClick={() => onSelectIssue(issueKey)}
          >
            {issueKey}
          </button>
        </li>
      ))}
    </ul>
  );
}

function getMetricImpact(status: MetricStatus): MetricImpact {
  if (status === "good") {
    return "positive";
  }
  if (status === "critical" || status === "warning") {
    return "negative";
  }
  return "unknown";
}

function getMetricContext(
  metricName: keyof SprintMetricValues,
  metrics: SprintMetricsResponse,
  confidence: DeliveryConfidenceDetail | null
) {
  const value = metrics.metrics[metricName];
  if (value === null) {
    return "Not enough data yet";
  }

  if (metricName === "completed_scope_pct") {
    if (confidence) {
      return `${Number(confidence.inputs.completed_effective_points.toFixed(2))} of ${Number(confidence.inputs.committed_effective_points.toFixed(2))} pts completed`;
    }
    return `${formatPercent(value)} of current sprint scope is done`;
  }
  if (metricName === "open_blockers") {
    return value === 0 ? "No open blockers" : `${value} open blockers`;
  }
  if (metricName === "open_high_severity_bugs") {
    return value === 0 ? "No open high-severity bugs" : `${value} open high-severity bugs`;
  }
  if (metricName === "bugs_created_during_sprint") {
    return value === 0 ? "No sprint-created bugs" : `${value} bugs created in sprint window`;
  }
  if (metricName === "median_cycle_time_days") {
    return `${formatMetricValue(metricName, value)} day median cycle time`;
  }
  if (metricName === "reopen_rate_pct") {
    return value === 0
      ? "No reopen events among eligible tickets"
      : `${formatPercent(value)} (${value.toFixed(2)} reopen events per 100 eligible tickets)`;
  }
  if (metricName === "rollover_count") {
    return value === 0
      ? "No unfinished tickets in the closed sprint scope"
      : `${value} current closed-sprint tickets unfinished`;
  }
  return sprintMetricLabels[metricName];
}

function buildBaseMetricEvaluation(
  metricName: keyof SprintMetricValues,
  metrics: SprintMetricsResponse
): MetricEvaluation {
  const value = metrics.metrics[metricName];
  const status = getMetricStatus(metricName, value);
  const formattedValue = formatMetricValue(metricName, value);
  const label = sprintMetricLabels[metricName];
  const group: MetricEvaluation["group"] = metricName === "completed_scope_pct"
    ? "delivery"
    : metricName === "open_high_severity_bugs" || metricName === "bugs_created_during_sprint" || metricName === "reopen_rate_pct"
    ? "quality"
    : metricName === "median_cycle_time_days"
    ? "flow"
    : "risk";

  let focusMessage = `${label} needs attention.`;
  if (metricName === "completed_scope_pct") {
    focusMessage = `Completed scope is ${status === "critical" ? "critical" : "at watch level"} at ${formattedValue}.`;
  } else if (metricName === "open_high_severity_bugs") {
    focusMessage = "Open high-severity bugs require attention.";
  } else if (metricName === "open_blockers") {
    focusMessage = "Open blockers require attention.";
  } else if (metricName === "rollover_count") {
    focusMessage = `Unfinished closed-sprint scope is ${formattedValue}.`;
  } else if (metricName === "reopen_rate_pct") {
    focusMessage = `Reopen events per 100 eligible tickets are ${formattedValue}.`;
  } else if (metricName === "median_cycle_time_days") {
    focusMessage = `Median cycle time is ${formattedValue} days.`;
  } else if (metricName === "bugs_created_during_sprint") {
    focusMessage = "Sprint-created bugs are adding quality load.";
  }

  return {
    key: metricName,
    label,
    group,
    status,
    value,
    formattedValue,
    focusMessage,
  };
}

function renderDeliveryConfidence(confidence: DeliveryConfidenceDetail) {
  const biggestDrag = getBiggestDrag(confidence.components);
  const progress = calculateExpectedVsActualProgress(confidence.inputs);
  const riskDrivers = getRiskDrivers(confidence.components);

  function formatProgressValue(value: number | null) {
    return value === null ? "N/A" : `${roundPercent(value)}%`;
  }

  function formatPoints(value: number) {
    return `${Math.round(value)} pts`;
  }

  function formatSnapshotPercent(value: number | null | undefined) {
    return value === null || value === undefined ? "N/A" : `${roundPercent(value)}%`;
  }

  function formatBlockedWork(value: number) {
    return `${roundPercent(value * 100)}%`;
  }

  return (
    <div className="confidence-decision-layout">
      <article className={`confidence-callout confidence-callout-${biggestDrag.status.level}`}>
        <h3>Biggest Drag</h3>
        <p>{biggestDrag.label} is the largest contributor to reduced confidence.</p>
      </article>

      <section className="confidence-section">
        <div className="confidence-section-heading">
          <h3>Expected vs Actual Progress</h3>
        </div>
        <dl className="confidence-progress-grid">
          <div>
            <dt>Expected</dt>
            <dd>{formatProgressValue(progress.expectedProgress)}</dd>
          </div>
          <div>
            <dt>Actual</dt>
            <dd>{formatProgressValue(progress.actualProgress)}</dd>
          </div>
          <div>
            <dt>Gap</dt>
            <dd className={progress.gap !== null && progress.gap < 0 ? "confidence-value-danger" : undefined}>
              {formatProgressValue(progress.gap)}
            </dd>
          </div>
        </dl>
      </section>

      <section className="confidence-section">
        <div className="confidence-section-heading">
          <h3>Risk Drivers</h3>
        </div>
        {riskDrivers.length > 0 ? (
          <ul className="confidence-risk-list">
            {riskDrivers.map((driver) => (
              <li className={`confidence-risk-driver risk-${driver.severity}`} key={driver.message}>
                <span className="confidence-risk-icon" aria-hidden="true" />
                {driver.message}
              </li>
            ))}
          </ul>
        ) : (
          <p className="muted">No threshold-based risk drivers detected.</p>
        )}
      </section>

      <section className="confidence-section">
        <div className="confidence-section-heading">
          <h3>Sprint Snapshot</h3>
        </div>
        <dl className="confidence-inputs">
          <dt>Current pointed scope</dt>
          <dd>{formatPoints(confidence.inputs.committed_effective_points)}</dd>
          <dt>Completed scope</dt>
          <dd>{formatPoints(confidence.inputs.completed_effective_points)}</dd>
          <dt>Remaining scope</dt>
          <dd>{formatPoints(confidence.inputs.remaining_effective_points)}</dd>
          <dt>Sprint elapsed</dt>
          <dd>{formatSnapshotPercent(confidence.inputs.time_elapsed_pct)}</dd>
          <dt>Historical velocity</dt>
          <dd>{confidence.inputs.historical_velocity === null ? "N/A" : formatPoints(confidence.inputs.historical_velocity)}</dd>
          <dt>Scope changes</dt>
          <dd>{Math.round(confidence.inputs.scope_change_count)}</dd>
          <dt>Blocked work</dt>
          <dd>{formatBlockedWork(confidence.inputs.blocked_issue_ratio)}</dd>
        </dl>
      </section>

      <section className="confidence-section confidence-trend-placeholder">
        <div className="confidence-section-heading">
          <h3>Delivery confidence in this sprint</h3>
        </div>
        <p className="muted">Confidence trend will appear after multiple snapshots are collected.</p>
      </section>
    </div>
  );
}

const heatmapGroups = ["Delivery", "Quality", "Flow", "Risk"] as const;

const heatmapStatusLabels: Record<RiskHeatmapStatus, string> = {
  healthy: "Healthy",
  watch: "Watch",
  risk: "Risk",
  critical: "Critical",
  neutral: "No data",
};

function renderRiskHeatmap(rows: SprintChartHistoryPoint[], cells: RiskHeatmapCell[]) {
  if (rows.length === 0) {
    return <p className="muted">Risk heatmap requires recent sprint metrics.</p>;
  }
  const statusByCell = new Map(cells.map((cell) => [`${cell.group}-${cell.sprint_id}`, cell.status]));

  return (
    <div className="risk-heatmap" role="table" aria-label="Sprint health heatmap">
      <div className="risk-heatmap-row risk-heatmap-header" role="row">
        <span role="columnheader">Area</span>
        {rows.map((row) => (
          <span role="columnheader" key={row.sprint_id}>
            {row.name}
          </span>
        ))}
      </div>
      {heatmapGroups.map((group) => (
        <div className="risk-heatmap-row" role="row" key={group}>
          <span className="risk-heatmap-group" role="rowheader">
            {group}
          </span>
          {rows.map((row) => {
            const status = statusByCell.get(`${group}-${row.sprint_id}`) ?? "neutral";
            return (
              <span
                className={`risk-heatmap-cell heatmap-${status}`}
                role="cell"
                key={`${group}-${row.sprint_id}`}
                title={`${group}: ${heatmapStatusLabels[status]}`}
              >
                {heatmapStatusLabels[status]}
              </span>
            );
          })}
        </div>
      ))}
    </div>
  );
}

function formatDate(value: string | null) {
  if (!value) {
    return "N/A";
  }
  return new Date(value).toLocaleDateString();
}

function normalizeProjectKey(projectKey: string | null | undefined) {
  const normalized = projectKey?.trim().toUpperCase();
  return normalized ? normalized : null;
}

function sprintMatchesProject(sprint: Sprint | null, projectKey: string | null) {
  if (!sprint || !projectKey) {
    return false;
  }
  return normalizeProjectKey(sprint.project_key) === projectKey;
}

function buildOptions(currentSprint: Sprint | null, closedSprints: Sprint[]): SprintOption[] {
  const options: SprintOption[] = [];
  if (currentSprint) {
    options.push({ label: `Current: ${currentSprint.name}`, sprint: currentSprint });
  }
  for (const sprint of closedSprints) {
    options.push({ label: `Closed: ${sprint.name}`, sprint });
  }
  return options;
}

function sprintSortTime(sprint: Sprint) {
  const primaryDate = sprint.complete_date ?? sprint.end_date ?? sprint.start_date ?? sprint.created_at;
  const parsed = Date.parse(primaryDate);
  return Number.isFinite(parsed) ? parsed : 0;
}

function getRecentSprints(sprints: Sprint[]) {
  return [...sprints]
    .sort((left, right) => sprintSortTime(right) - sprintSortTime(left))
    .slice(0, 5)
    .reverse();
}

function isNotClosedSprint(sprint: Sprint) {
  return sprint.state.trim().toLowerCase() !== "closed";
}

async function loadAllSprintIssues(sprintId: string) {
  const items: SprintIssue[] = [];
  let fetchedCount = 0;
  let total = 0;

  while (true) {
    const response = await apiClient.getSprintIssues(sprintId, fetchedCount, sprintIssuePageSize);
    total = response.total;
    items.push(...response.items);
    fetchedCount += response.items.length;
    if (fetchedCount >= total || response.items.length === 0) {
      break;
    }
  }

  return items;
}

export function SprintsPanel({ refreshNonce, onSelectIssue, mode = "intelligence", projectKey = null }: SprintsPanelProps) {
  const activeProjectKey = normalizeProjectKey(projectKey);
  const [currentSprint, setCurrentSprint] = useState<Sprint | null>(null);
  const [closedSprints, setClosedSprints] = useState<Sprint[]>([]);
  const [selectedSprintId, setSelectedSprintId] = useState<string | null>(null);
  const [metrics, setMetrics] = useState<SprintMetricsResponse | null>(null);
  const [issues, setIssues] = useState<SprintIssue[]>([]);
  const [isLoadingList, setIsLoadingList] = useState(true);
  const [isLoadingDetails, setIsLoadingDetails] = useState(false);
  const [isSprintHealthStatsExpanded, setIsSprintHealthStatsExpanded] = useState(true);
  const [isTicketSituationExpanded, setIsTicketSituationExpanded] = useState(false);
  const [isDeliveryConfidenceExpanded, setIsDeliveryConfidenceExpanded] = useState(true);
  const [isSprintMetricsExpanded, setIsSprintMetricsExpanded] = useState(true);
  const [isSprintChartsExpanded, setIsSprintChartsExpanded] = useState(true);
  const [snapshotBaseline, setSnapshotBaseline] = useState<SnapshotBaseline>("previous");
  const [snapshotComparison, setSnapshotComparison] = useState<SnapshotComparisonResponse | null>(null);
  const [snapshotHistory, setSnapshotHistory] = useState<SnapshotChangeHistoryResponse | null>(null);
  const [isLoadingSnapshotChanges, setIsLoadingSnapshotChanges] = useState(false);
  const [snapshotChangeError, setSnapshotChangeError] = useState<string | null>(null);
  const [sprintChartRows, setSprintChartRows] = useState<SprintChartHistoryPoint[]>([]);
  const [sprintChartRefreshNonce, setSprintChartRefreshNonce] = useState(0);
  const [isLoadingSprintConfidence, setIsLoadingSprintConfidence] = useState(false);
  const [sprintConfidenceError, setSprintConfidenceError] = useState<string | null>(null);

  const issuesByKey = useMemo(() => {
    const map: Record<string, SprintIssue> = {};
    for (const issue of issues) {
      map[issue.issue_key] = issue;
    }
    return map;
  }, [issues]);
  const [isRecomputing, setIsRecomputing] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const scopedCurrentSprint = sprintMatchesProject(currentSprint, activeProjectKey) ? currentSprint : null;
  const scopedClosedSprints = useMemo(
    () => closedSprints.filter((sprint) => sprintMatchesProject(sprint, activeProjectKey)),
    [activeProjectKey, closedSprints]
  );
  const options = useMemo(() => buildOptions(scopedCurrentSprint, scopedClosedSprints), [scopedCurrentSprint, scopedClosedSprints]);
  const selectedScopedSprintId = options.some((option) => option.sprint.sprint_id === selectedSprintId) ? selectedSprintId : null;
  const selectedSprint = options.find((option) => option.sprint.sprint_id === selectedScopedSprintId)?.sprint ?? null;
  const recentSprints = useMemo(() => {
    const sprintsById = new Map<string, Sprint>();
    if (scopedCurrentSprint) {
      sprintsById.set(scopedCurrentSprint.sprint_id, scopedCurrentSprint);
    }
    for (const sprint of scopedClosedSprints) {
      sprintsById.set(sprint.sprint_id, sprint);
    }
    return getRecentSprints(Array.from(sprintsById.values()));
  }, [scopedCurrentSprint, scopedClosedSprints]);
  const sprintConfidenceRows = useMemo(
    () =>
      sprintChartRows.map((row) => ({
        sprint_id: row.sprint_id,
        name: row.name,
        delivery_confidence: row.delivery_confidence,
        confidence_delta: row.confidence_delta,
        is_not_closed: row.is_not_closed,
      })),
    [sprintChartRows]
  );
  const sprintCommitmentReliabilityRows = useMemo<SprintCommitmentReliabilityRow[]>(
    () =>
      sprintChartRows.map((row) => ({
        sprint_id: row.sprint_id,
        name: row.name,
        committed_story_points: row.committed_story_points,
        completed_story_points: row.completed_story_points,
        reliability_pct: row.reliability_pct,
        predictability_avg: row.predictability_avg,
        is_not_closed: row.is_not_closed,
      })),
    [sprintChartRows]
  );
  const storyPointUi = buildSprintStoryPointUiVisibility(metrics);
  const storyPointUnavailableReason = getSprintStoryPointUnavailableReason(metrics);
  const storyPointExplanations = metrics?.delivery_confidence_explanations ?? [];
  const storyPointUnavailableMessage = storyPointExplanations[0] ?? storyPointUnavailableReason;
  const deliveryConfidenceMissingIssueKeys = metrics?.metric_availability?.metrics
    .delivery_confidence_score?.missing_issue_keys ?? [];
  const hasStoryPointMetrics = storyPointUi.hasStoryPointMetrics;
  const predictabilityRows = useMemo(
    () =>
      hasStoryPointMetrics
        ? sprintCommitmentReliabilityRows
        .filter(
          (
            row
          ): row is SprintCommitmentReliabilityRow & {
            committed_story_points: number;
            completed_story_points: number;
          } => row.committed_story_points !== null && row.completed_story_points !== null
        )
        .map((row) => ({
          sprint_id: row.sprint_id,
          name: row.name,
          committed_story_points: row.committed_story_points,
          completed_story_points: row.completed_story_points,
          is_not_closed: row.is_not_closed,
        }))
        : [],
    [hasStoryPointMetrics, sprintCommitmentReliabilityRows]
  );
  const predictabilityCard = useMemo(
    () => (storyPointUi.showTeamPredictability ? buildPredictabilityDisplayModel(predictabilityRows) : null),
    [storyPointUi.showTeamPredictability, predictabilityRows]
  );
  const workDistributionCard = useMemo(
    () => buildWorkDistributionDisplayModel(metrics?.workload_distribution),
    [metrics?.workload_distribution]
  );
  const sprintWorkStateCard = useMemo(
    () => (metrics ? buildSprintWorkStateDisplayModel(metrics, issues) : null),
    [metrics, issues]
  );
  const deliveryConfidence = storyPointUi.showPointValues ? metrics?.delivery_confidence ?? null : null;
  const confidenceBreakdown = storyPointUi.showDeliveryConfidenceBreakdown ? metrics?.confidence_breakdown ?? null : null;
  const biggestDeliveryDriver = hasStoryPointMetrics ? metrics?.biggest_driver ?? null : null;
  const scopeCreepCard = useMemo(
    () => (deliveryConfidence ? buildScopeCreepDisplayModel(deliveryConfidence) : null),
    [deliveryConfidence]
  );
  const velocityHealthCard = useMemo(
    () => (deliveryConfidence && storyPointUi.showVelocityHealth ? buildVelocityHealthDisplayModel(deliveryConfidence) : null),
    [deliveryConfidence, storyPointUi.showVelocityHealth]
  );
  const deliveryConfidenceStatus = deliveryConfidence
    ? getConfidenceStatus(deliveryConfidence.score)
    : null;
  const metricEvaluations = useMemo(() => {
    if (!metrics) {
      return [];
    }
    const evaluations: MetricEvaluation[] = [];
    if (scopeCreepCard) {
      const value = deliveryConfidence?.inputs.scope_stability_index === null || !deliveryConfidence
        ? null
        : Number((deliveryConfidence.inputs.scope_stability_index * 100).toFixed(2));
      evaluations.push({
        key: "scope_creep",
        label: "Scope creep",
        group: "delivery",
        status: scopeCreepCard.status,
        value,
        formattedValue: scopeCreepCard.value,
        focusMessage: `Scope creep is ${scopeCreepCard.status === "critical" ? "critical" : "at watch level"} at ${scopeCreepCard.value}.`,
      });
    }
    if (velocityHealthCard) {
      const average = deliveryConfidence?.inputs.historical_velocity;
      const completed = deliveryConfidence?.inputs.completed_effective_points;
      const value = average && average > 0 && completed !== undefined ? Number(((completed / average) * 100).toFixed(0)) : null;
      evaluations.push({
        key: "velocity_health",
        label: "Velocity health",
        group: "delivery",
        status: velocityHealthCard.status,
        value,
        formattedValue: velocityHealthCard.value,
        focusMessage: value === null ? "Velocity health needs more closed sprint data." : `Velocity health is only ${velocityHealthCard.value} of normal.`,
      });
    }
    evaluations.push(buildBaseMetricEvaluation("open_high_severity_bugs", metrics));
    evaluations.push(buildBaseMetricEvaluation("completed_scope_pct", metrics));
    evaluations.push(buildBaseMetricEvaluation("open_blockers", metrics));
    evaluations.push(buildBaseMetricEvaluation("rollover_count", metrics));
    evaluations.push(buildBaseMetricEvaluation("reopen_rate_pct", metrics));
    evaluations.push(buildBaseMetricEvaluation("median_cycle_time_days", metrics));
    evaluations.push(buildBaseMetricEvaluation("bugs_created_during_sprint", metrics));
    if (workDistributionCard) {
      evaluations.push({
        key: "work_distribution",
        label: "Workload concentration",
        group: "risk",
        status: workDistributionCard.status,
        value: Number.parseFloat(workDistributionCard.value),
        formattedValue: workDistributionCard.value,
        focusMessage: `Workload concentration is ${workDistributionCard.value} for the top assignee.`,
      });
    }
    if (predictabilityCard) {
      evaluations.push({
        key: "team_predictability",
        label: "Team predictability",
        group: "delivery",
        status: predictabilityCard.status,
        value: Number.parseFloat(predictabilityCard.value),
        formattedValue: predictabilityCard.value,
        focusMessage: `Team predictability is ${predictabilityCard.value}.`,
      });
    }
    return evaluations;
  }, [deliveryConfidence, metrics, predictabilityCard, scopeCreepCard, velocityHealthCard, workDistributionCard]);
  const focusAreas = useMemo(() => generateFocusAreas(metricEvaluations), [metricEvaluations]);
  const riskHeatmapCells = useMemo(() => buildRiskHeatmapRows(sprintChartRows), [sprintChartRows]);
  const latestConfidenceDelta = sprintConfidenceRows.length > 1
    ? sprintConfidenceRows[sprintConfidenceRows.length - 1].confidence_delta
    : null;
  const hasConfidenceTrend = storyPointUi.showDeliveryConfidenceTrend && hasChartData(sprintChartRows, ["delivery_confidence"]);
  const hasConfidenceBreakdown = storyPointUi.showDeliveryConfidenceBreakdown && hasChartData(sprintChartRows, [
    "progress_alignment",
    "velocity_fit",
    "scope_stability",
    "blocker_health",
  ]);
  const hasCommitmentTrend = storyPointUi.showCommitmentReliability && hasChartData(sprintCommitmentReliabilityRows, [
    "committed_story_points",
    "completed_story_points",
  ]);
  const hasReliabilityTrend = storyPointUi.showCommitmentReliability && hasChartData(sprintCommitmentReliabilityRows, ["reliability_pct"]);
  const hasPredictabilityTrend = storyPointUi.showTeamPredictability && sprintCommitmentReliabilityRows.some((row) => row.predictability_avg !== null);
  const hasScopeTrend = hasChartData(sprintChartRows, ["scope_change_count", "scope_creep_pct"]);
  const hasQualityCountTrend = hasChartData(sprintChartRows, [
    "open_high_severity_bugs",
    "bugs_created_during_sprint",
  ]);
  const hasReopenTrend = hasChartData(sprintChartRows, ["reopen_rate_pct"]);
  const hasFlowTrend = hasChartData(sprintChartRows, ["median_cycle_time_days"]);

  function formatChartValue(value: number, name: string) {
    const formatted = Number(value.toFixed(2));
    if (
      name.includes("%") ||
      name.includes("Confidence") ||
      name.includes("Reliability") ||
      name.includes("Progress") ||
      name.includes("Velocity") ||
      name.includes("Blocker") ||
      name.includes("Scope Stability") ||
      name.includes("Reopen") ||
      name.includes("Predictability")
    ) {
      return `${formatted}%`;
    }
    if (name.includes("Cycle time")) {
      return `${formatted} days`;
    }
    return String(formatted);
  }

  function formatDeltaText(delta: number | null) {
    if (delta === null) {
      return null;
    }
    if (delta === 0) {
      return "No change from previous sprint";
    }
    return `${delta > 0 ? "+" : ""}${Number(delta.toFixed(2))}% from previous sprint`;
  }

  function renderSprintMetricCard(metricName: keyof SprintMetricValues) {
    if (!metrics || metricName === "delivery_confidence_score") {
      return null;
    }
    const value = metrics.metrics[metricName];
    const availabilityDisplay = getSprintMetricDisplay(metrics, metricName);
    const availabilityExplanations = availabilityDisplay.explanations.filter(
      (explanation) => explanation !== availabilityDisplay.reason
    );
    const missingStatusDetail = availabilityDisplay.missingIssueKeys.length > 0
      ? `Missing status: ${availabilityDisplay.missingIssueKeys.join(", ")}`
      : null;
    const status = availabilityDisplay.isAvailable ? getMetricStatus(metricName, value) : "neutral";
    return (
      <MetricStatusCard
        key={metricName}
        title={sprintMetricLabels[metricName]}
        value={availabilityDisplay.value ?? formatMetricValue(metricName, value)}
        status={status}
        comparison={getMetricContext(metricName, metrics, deliveryConfidence)}
        comparisonImpact={getMetricImpact(status)}
        details={[
          ...(availabilityDisplay.reason ? [availabilityDisplay.reason] : []),
          ...availabilityExplanations,
          ...(missingStatusDetail ? [missingStatusDetail] : []),
        ]}
        infoText={availabilityDisplay.reason ?? sprintMetricInfoText[metricName]}
        badge={availabilityDisplay.badge}
        badgeTitle={availabilityDisplay.reason}
      >
        {renderMetricIssueKeys(metricName, value, metrics, issuesByKey, onSelectIssue)}
      </MetricStatusCard>
    );
  }

  useEffect(() => {
    setCurrentSprint(null);
    setClosedSprints([]);
    setSelectedSprintId(null);
    setMetrics(null);
    setIssues([]);
    setSnapshotComparison(null);
    setSnapshotHistory(null);
    setSnapshotChangeError(null);
    setSprintChartRows([]);
    setSprintConfidenceError(null);
    setIsLoadingDetails(false);
    setIsLoadingSnapshotChanges(false);
    setIsLoadingSprintConfidence(false);
  }, [activeProjectKey]);

  useEffect(() => {
    let isActive = true;

    async function loadSprintList() {
      if (!activeProjectKey) {
        setCurrentSprint(null);
        setClosedSprints([]);
        setSelectedSprintId(null);
        setIsLoadingList(false);
        return;
      }

      setIsLoadingList(true);
      setErrorMessage(null);
      try {
        const [currentResult, closedResult] = await Promise.allSettled([
          apiClient.getCurrentSprint(activeProjectKey),
          apiClient.getClosedSprints(activeProjectKey),
        ]);
        if (!isActive) {
          return;
        }
        const activeSprint = currentResult.status === "fulfilled" && sprintMatchesProject(currentResult.value.item, activeProjectKey)
          ? currentResult.value.item
          : null;
        const closed = closedResult.status === "fulfilled"
          ? closedResult.value.items.filter((sprint) => sprintMatchesProject(sprint, activeProjectKey))
          : [];
        setCurrentSprint(activeSprint);
        setClosedSprints(closed);
        setSelectedSprintId(activeSprint?.sprint_id ?? closed[0]?.sprint_id ?? null);
        if (closedResult.status === "rejected") {
          setErrorMessage(closedResult.reason instanceof Error ? closedResult.reason.message : "Failed to load sprints.");
        }
      } finally {
        if (isActive) {
          setIsLoadingList(false);
        }
      }
    }

    void loadSprintList();

    return () => {
      isActive = false;
    };
  }, [activeProjectKey, refreshNonce]);

  useEffect(() => {
    if (!selectedScopedSprintId) {
      setMetrics(null);
      setIssues([]);
      return;
    }

    const sprintId = selectedScopedSprintId;
    let isActive = true;

    async function loadSprintDetails() {
      setIsLoadingDetails(true);
      setErrorMessage(null);
      try {
        const [metricsResponse, issueResponse] = await Promise.all([
          apiClient.getSprintMetrics(sprintId),
          loadAllSprintIssues(sprintId),
        ]);
        if (!isActive) {
          return;
        }
        setMetrics(metricsResponse);
        setIssues(issueResponse);
      } catch (error) {
        if (isActive) {
          setErrorMessage(error instanceof Error ? error.message : "Failed to load sprint details.");
        }
      } finally {
        if (isActive) {
          setIsLoadingDetails(false);
        }
      }
    }

    void loadSprintDetails();

    return () => {
      isActive = false;
    };
  }, [selectedScopedSprintId]);

  useEffect(() => {
    if (mode !== "reports" || !selectedScopedSprintId) {
      setSnapshotComparison(null);
      setSnapshotHistory(null);
      return;
    }

    const sprintId = selectedScopedSprintId;
    let isActive = true;

    async function loadSnapshotChanges() {
      setIsLoadingSnapshotChanges(true);
      setSnapshotChangeError(null);
      try {
        const [comparison, history] = await Promise.all([
          apiClient.getSprintSnapshotComparison(sprintId, snapshotBaseline),
          apiClient.getSprintSnapshotChangeHistory(sprintId),
        ]);
        if (isActive) {
          setSnapshotComparison(comparison);
          setSnapshotHistory(history);
        }
      } catch (error) {
        if (isActive) {
          setSnapshotChangeError(error instanceof Error ? error.message : "Failed to load snapshot changes.");
          setSnapshotComparison(null);
          setSnapshotHistory(null);
        }
      } finally {
        if (isActive) {
          setIsLoadingSnapshotChanges(false);
        }
      }
    }

    void loadSnapshotChanges();

    return () => {
      isActive = false;
    };
  }, [mode, selectedScopedSprintId, snapshotBaseline, refreshNonce, sprintChartRefreshNonce]);

  useEffect(() => {
    if (recentSprints.length === 0) {
      setSprintChartRows([]);
      return;
    }

    let isActive = true;

    async function loadSprintConfidence() {
      setIsLoadingSprintConfidence(true);
      setSprintConfidenceError(null);
      try {
        const sources = await Promise.all(
          recentSprints.map(async (sprint) => {
            const response = await apiClient.getSprintMetrics(sprint.sprint_id);
            return {
              sprint_id: sprint.sprint_id,
              name: sprint.name,
              is_not_closed: isNotClosedSprint(sprint),
              metrics: response,
            };
          })
        );

        if (isActive) {
          setSprintChartRows(buildSprintChartHistory(sources));
        }
      } catch (error) {
        if (isActive) {
          setSprintConfidenceError(error instanceof Error ? error.message : "Failed to load sprint confidence.");
        }
      } finally {
        if (isActive) {
          setIsLoadingSprintConfidence(false);
        }
      }
    }

    void loadSprintConfidence();

    return () => {
      isActive = false;
    };
  }, [recentSprints, refreshNonce, sprintChartRefreshNonce]);

  async function handleRecomputeSprint() {
    if (!selectedScopedSprintId || isRecomputing) {
      return;
    }
    setIsRecomputing(true);
    setErrorMessage(null);
    try {
      await apiClient.recomputeSprint(selectedScopedSprintId);
      const [metricsResponse, issueResponse] = await Promise.all([
        apiClient.getSprintMetrics(selectedScopedSprintId),
        loadAllSprintIssues(selectedScopedSprintId),
      ]);
      setMetrics(metricsResponse);
      setIssues(issueResponse);
      setSprintChartRefreshNonce((current) => current + 1);
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : "Failed to recompute sprint metrics.");
    } finally {
      setIsRecomputing(false);
    }
  }

  return (
    <div className="sprints-panel">
      {errorMessage ? <div className="panel error-panel">{errorMessage}</div> : null}

      {mode === "intelligence" ? (
        <section className="panel report-export-panel">
          <div className="panel-heading">
            <div>
              <h2>Executive Reporting</h2>
            </div>
            <ReportExportActions
              entity="sprint"
              entityId={selectedScopedSprintId}
              filenameLabel={selectedSprint?.name ?? selectedScopedSprintId ?? "sprint"}
            />
          </div>
        </section>
      ) : null}

      {mode === "intelligence" ? (
      <section className="panel delivery-confidence-panel">
        <div className="panel-heading">
          <div className="delivery-confidence-heading">
            <h2 className="delivery-confidence-title">
              Delivery Confidence
              <button
                type="button"
                className="info-button"
                title="Delivery confidence is a weighted sprint health score. It combines progress alignment, velocity fit, blocker health, and scope stability to produce a single confidence value."
                aria-label="Delivery confidence info"
              >
                i
              </button>
            </h2>
            {deliveryConfidence && deliveryConfidenceStatus ? (
              <div className="delivery-confidence-decision" aria-label={`Delivery confidence ${formatConfidencePercent(deliveryConfidence.score)}, ${deliveryConfidenceStatus.label}`}>
                <strong className={`delivery-confidence-score confidence-status-text-${deliveryConfidenceStatus.level}`}>
                  {formatConfidencePercent(deliveryConfidence.score)}
                </strong>
                <span className={`confidence-status-pill confidence-status-${deliveryConfidenceStatus.level}`}>
                  {deliveryConfidenceStatus.label}
                </span>
              </div>
            ) : null}
          </div>
          <div className="panel-heading-actions">
            {metrics?.ruleset_label ? <span className="muted">{metrics.ruleset_label}</span> : null}
            {deliveryConfidence ? (
              <button
                type="button"
                className="secondary-button compact-button"
                aria-expanded={isDeliveryConfidenceExpanded}
                onClick={() => setIsDeliveryConfidenceExpanded((c) => !c)}
              >
                {isDeliveryConfidenceExpanded ? "Minimize" : "Expand"}
              </button>
            ) : null}
          </div>
        </div>
        {isLoadingDetails ? <p className="muted">Loading delivery confidence...</p> : null}
        {!isLoadingDetails && metrics && !metrics.is_computed ? (
          <p className="muted">Sprint metrics have not been computed yet.</p>
        ) : null}
        {!isLoadingDetails && storyPointUi.showStoryPointUnavailableMessage ? (
          <div className="muted">
            {metrics?.delivery_confidence_status === "INCONCLUSIVE" ? (
              <p>
                <span className="metric-muted-badge">Inconclusive</span>
              </p>
            ) : null}
            {storyPointExplanations.map((explanation) => <p key={explanation}>{explanation}</p>)}
            {deliveryConfidenceMissingIssueKeys.length > 0 ? (
              <p>Missing evidence: {deliveryConfidenceMissingIssueKeys.join(", ")}</p>
            ) : null}
          </div>
        ) : null}
        {!isLoadingDetails && deliveryConfidence ? (
          <p className="delivery-confidence-summary">
            {getDeliveryConfidenceSummary(deliveryConfidence.components)}
          </p>
        ) : null}
        {!isLoadingDetails && confidenceBreakdown ? (
          <ConfidenceBreakdownCard breakdown={confidenceBreakdown} />
        ) : null}
        {!isLoadingDetails && biggestDeliveryDriver ? (
          <BiggestDriverCard driver={biggestDeliveryDriver} heading="Biggest Delivery Drag" />
        ) : null}
        {!isLoadingDetails && metrics ? (
          <RecommendationsPanel
            recommendations={metrics.recommendations}
            title="Sprint Recommended Actions"
          />
        ) : null}
        {!isLoadingDetails && deliveryConfidence && isDeliveryConfidenceExpanded
          ? renderDeliveryConfidence(deliveryConfidence)
          : null}
      </section>
      ) : null}

      {mode === "intelligence" ? (
      <section className="panel metrics-panel">
        <div className="panel-heading">
          <h2>Metrics</h2>
          <div className="panel-heading-actions">
            <button
              type="button"
              className="secondary-button compact-button"
              aria-expanded={isSprintMetricsExpanded}
              onClick={() => setIsSprintMetricsExpanded((current) => !current)}
            >
              {isSprintMetricsExpanded ? "Minimize" : "Expand"}
            </button>
          </div>
        </div>
        {isSprintMetricsExpanded ? (
          <>
            {isLoadingDetails ? <p className="muted">Loading sprint metrics...</p> : null}
            {!isLoadingDetails && metrics && !metrics.is_computed ? (
              <p className="muted">Sprint metrics have not been computed yet.</p>
            ) : null}
            {!isLoadingDetails && metrics?.is_computed ? (
              <div className="metric-category-stack">
                <section className="focus-areas-section">
                  <h3>Focus Areas</h3>
                  <ol className="focus-area-list">
                    {focusAreas.map((area) => (
                      <li key={area}>{area}</li>
                    ))}
                  </ol>
                </section>
                <MetricCategorySection title="Delivery" summary={getGroupSummary("delivery", metricEvaluations)}>
                  {renderSprintMetricCard("committed_scope")}
                  {renderSprintMetricCard("completed_scope_pct")}
                  {scopeCreepCard ? (
                    <MetricStatusCard
                      title="Scope creep"
                      value={scopeCreepCard.value}
                      status={scopeCreepCard.status}
                      comparison={scopeCreepCard.comparison}
                      comparisonImpact={scopeCreepCard.impact}
                      details={scopeCreepCard.details}
                      infoText="High scope creep reduces predictability."
                    >
                      {renderScopeIssueKeys(
                        "Affected issues",
                        scopeCreepCard.issueKeys,
                        issuesByKey,
                        onSelectIssue,
                        scopeCreepCard.hiddenIssueCount
                      )}
                    </MetricStatusCard>
                  ) : null}
                  {velocityHealthCard ? (
                    <MetricStatusCard
                      title="Velocity health"
                      value={velocityHealthCard.value}
                      status={velocityHealthCard.status}
                      comparison={velocityHealthCard.comparison}
                      comparisonImpact={velocityHealthCard.impact}
                      details={velocityHealthCard.details}
                      infoText="Compares current completed work to historical sprint velocity."
                    />
                  ) : null}
                  {predictabilityCard ? (
                    <MetricStatusCard
                      title="Team predictability"
                      value={predictabilityCard.value}
                      status={predictabilityCard.status}
                      comparison={predictabilityCard.comparison}
                      comparisonImpact={predictabilityCard.impact}
                      details={predictabilityCard.details}
                      infoText="Shows how reliably recent closed sprints completed committed work."
                    />
                  ) : null}
                </MetricCategorySection>
                <MetricCategorySection title="Quality" summary={getGroupSummary("quality", metricEvaluations)}>
                  {renderSprintMetricCard("open_high_severity_bugs")}
                  {renderSprintMetricCard("bugs_created_during_sprint")}
                  {renderSprintMetricCard("reopen_rate_pct")}
                </MetricCategorySection>
                <MetricCategorySection title="Flow" summary={getGroupSummary("flow", metricEvaluations)}>
                  {renderSprintMetricCard("median_cycle_time_days")}
                </MetricCategorySection>
                <MetricCategorySection title="Risk" summary={getGroupSummary("risk", metricEvaluations)}>
                  {renderSprintMetricCard("open_blockers")}
                  {renderSprintMetricCard("rollover_count")}
                  <MetricStatusCard
                    title={workDistributionCard.title}
                    value={workDistributionCard.value}
                    status={workDistributionCard.status}
                    comparison={workDistributionCard.comparison}
                    comparisonImpact={workDistributionCard.impact}
                    details={workDistributionCard.details}
                    badge={workDistributionCard.badge}
                    badgeTitle={workDistributionCard.badgeTitle}
                    infoText="Shows whether active sprint work is concentrated with one assignee."
                  />
                </MetricCategorySection>
                {sprintWorkStateCard ? (
                  <MetricCategorySection title="Sprint Work State" summary={getGroupSummary("snapshot", metricEvaluations)}>
                    <MetricStatusCard
                      title="Sprint work state"
                      value={sprintWorkStateCard.value}
                      status={sprintWorkStateCard.status}
                      comparison={sprintWorkStateCard.comparison}
                      comparisonImpact={sprintWorkStateCard.impact}
                      details={sprintWorkStateCard.details}
                      infoText="Condenses current sprint scope, in-progress, not-started, done, and applicable unfinished closed-sprint work into one scan-friendly card."
                      badge={sprintWorkStateCard.badge}
                      badgeTitle={sprintWorkStateCard.badgeTitle}
                    />
                  </MetricCategorySection>
                ) : null}
              </div>
            ) : null}
          </>
        ) : null}
      </section>
      ) : null}

      {mode === "reports" ? (
      <section className="panel charts-panel">
        <div className="panel-heading">
          <h2>Charts</h2>
          <div className="panel-heading-actions">
            <button
              type="button"
              className="secondary-button compact-button"
              aria-expanded={isSprintChartsExpanded}
              onClick={() => setIsSprintChartsExpanded((current) => !current)}
            >
              {isSprintChartsExpanded ? "Minimize" : "Expand"}
            </button>
          </div>
        </div>
        {isSprintChartsExpanded ? (
          <>
            {storyPointUi.showStoryPointUnavailableMessage ? (
              <p className="muted">{storyPointUnavailableMessage}</p>
            ) : null}

            {storyPointUi.hasStoryPointMetrics ? (
              <>
                <SnapshotChangePanel
                  context="sprint"
                  comparison={snapshotComparison}
                  history={snapshotHistory}
                  baseline={snapshotBaseline}
                  isLoading={isLoadingSnapshotChanges}
                  error={snapshotChangeError}
                  onBaselineChange={setSnapshotBaseline}
                />

                {biggestDeliveryDriver ? (
                  <BiggestDriverCard driver={biggestDeliveryDriver} heading="Biggest Delivery Drag" />
                ) : null}

                <div id="delivery-confidence-history" className="chart-section-heading chart-section-hero">
                  <div>
                    <h3>Delivery Confidence Trend</h3>
                    <p className="chart-section-subtitle">
                      Is delivery health improving or slipping across recent sprints?
                    </p>
                  </div>
                  <div className="chart-heading-meta">
                    {sprintConfidenceRows.length > 0 ? <span className="muted">Last {sprintConfidenceRows.length}</span> : null}
                    {formatDeltaText(latestConfidenceDelta) ? (
                      <span className="chart-delta-pill">{formatDeltaText(latestConfidenceDelta)}</span>
                    ) : null}
                  </div>
                </div>
                {isLoadingSprintConfidence ? <p className="muted">Loading sprint chart history...</p> : null}
                {sprintConfidenceError ? <p className="error-text">{sprintConfidenceError}</p> : null}
                {!isLoadingSprintConfidence && !sprintConfidenceError && !hasConfidenceTrend ? (
                  <p className="muted">No sprint confidence data available yet.</p>
                ) : null}
                {!isLoadingSprintConfidence && !sprintConfidenceError && hasConfidenceTrend ? (
                  <MetricLineChart
                    data={sprintConfidenceRows}
                    height={380}
                    lines={[
                      {
                        key: "delivery_confidence",
                        label: "Delivery confidence",
                        color: MetricColors.sprintConfidence,
                      },
                    ]}
                    dataKey="name"
                    formatter={formatChartValue}
                    yDomain={[0, 100]}
                    yTickFormatter={(value) => `${Math.round(value)}%`}
                    referenceLines={[
                      { y: 80, label: "Healthy", color: MetricColors.sprintConfidence },
                      { y: 60, label: "Watch", color: MetricColors.confidenceWatch },
                      { y: 40, label: "Risk", color: MetricColors.confidenceCritical },
                    ]}
                  />
                ) : null}

                <div className="chart-section-heading">
                  <div>
                    <h3>Confidence Breakdown History</h3>
                    <p className="chart-section-subtitle">
                      Which confidence driver is pushing recent sprints up or down?
                    </p>
                  </div>
                </div>
                {!isLoadingSprintConfidence && !sprintConfidenceError && hasConfidenceBreakdown ? (
                  <MetricLineChart
                    data={sprintChartRows}
                    lines={[
                      {
                        key: "progress_alignment",
                        label: "Progress Alignment",
                        color: MetricColors.progressAlignment,
                      },
                      {
                        key: "velocity_fit",
                        label: "Velocity Fit",
                        color: MetricColors.velocityFit,
                      },
                      {
                        key: "scope_stability",
                        label: "Scope Stability",
                        color: MetricColors.scopeStability,
                      },
                      {
                        key: "blocker_health",
                        label: "Blocker Health",
                        color: MetricColors.blockerHealth,
                      },
                    ]}
                    dataKey="name"
                    formatter={formatChartValue}
                    yDomain={[0, 100]}
                    yTickFormatter={(value) => `${Math.round(value)}%`}
                  />
                ) : null}

                <div className="chart-section-heading">
                  <div>
                    <h3>Sprint Commitment Reliability</h3>
                    <p className="chart-section-subtitle">
                      Committed vs completed scope, with reliability percent and predictability trend when available.
                    </p>
                  </div>
                </div>
                {!isLoadingSprintConfidence && !sprintConfidenceError && !hasCommitmentTrend ? (
                  <p className="muted">No sprint commitment reliability data available yet.</p>
                ) : null}
                {!isLoadingSprintConfidence && !sprintConfidenceError && hasCommitmentTrend ? (
                  <>
                    <MetricMultiBarChart
                      data={sprintCommitmentReliabilityRows}
                      bars={[
                        {
                          key: "committed_story_points",
                          label: "Committed story points",
                          color: committedStoryPointColor,
                        },
                        {
                          key: "completed_story_points",
                          label: "Completed story points",
                          color: completedStoryPointColor,
                        },
                      ]}
                      dataKey="name"
                      formatter={formatChartValue}
                    />
                    {hasReliabilityTrend ? (
                      <MetricLineChart
                        data={sprintCommitmentReliabilityRows}
                        height={220}
                        lines={[
                          {
                            key: "reliability_pct",
                            label: "Reliability %",
                            color: MetricColors.scopeStability,
                          },
                          ...(hasPredictabilityTrend
                            ? [
                                {
                                  key: "predictability_avg",
                                  label: "Predictability avg",
                                  color: MetricColors.velocityFit,
                                },
                              ]
                            : []),
                        ]}
                        dataKey="name"
                        formatter={formatChartValue}
                        yDomain={[0, 120]}
                        yTickFormatter={(value) => `${Math.round(value)}%`}
                      />
                    ) : null}
                    {!hasPredictabilityTrend ? (
                      <p className="muted chart-empty-note">Predictability trend requires at least 3 closed sprints.</p>
                    ) : null}
                  </>
                ) : null}
              </>
            ) : null}

            {storyPointUi.showStoryPointChartEmptyState ? (
              <>
                <div id="delivery-confidence-history" className="chart-section-heading chart-section-hero">
                  <div>
                    <h3>Delivery Confidence Trend</h3>
                    <p className="chart-section-subtitle">
                      Is delivery health improving or slipping across recent sprints?
                    </p>
                  </div>
                </div>
                <p className="muted chart-empty-note">{storyPointUnavailableMessage}</p>

                <div className="chart-section-heading">
                  <div>
                    <h3>Confidence Breakdown History</h3>
                    <p className="chart-section-subtitle">
                      Which confidence driver is pushing recent sprints up or down?
                    </p>
                  </div>
                </div>
                <p className="muted chart-empty-note">{storyPointUnavailableMessage}</p>

                <div className="chart-section-heading">
                  <div>
                    <h3>Sprint Commitment Reliability</h3>
                    <p className="chart-section-subtitle">
                      Committed vs completed scope, with reliability percent and predictability trend when available.
                    </p>
                  </div>
                </div>
                <p className="muted chart-empty-note">{storyPointUnavailableMessage}</p>
              </>
            ) : null}

            <div className="chart-section-heading">
              <div>
                <h3>Scope Change Trend</h3>
                <p className="chart-section-subtitle">
                  Planning instability across recent sprints.
                </p>
              </div>
            </div>
            {!isLoadingSprintConfidence && !sprintConfidenceError && hasScopeTrend ? (
              <MetricMultiBarChart
                data={sprintChartRows}
                bars={[
                  { key: "scope_change_count", label: "Scope changes", color: MetricColors.scopeChurn },
                  { key: "scope_added_count", label: "Added issues", color: MetricColors.completedScope },
                  { key: "scope_removed_count", label: "Removed issues", color: MetricColors.bugs },
                  { key: "net_scope_change", label: "Net scope change", color: MetricColors.neutralRisk },
                ]}
                dataKey="name"
                formatter={formatChartValue}
              />
            ) : null}
            {!isLoadingSprintConfidence && !sprintConfidenceError && !hasScopeTrend ? (
              <p className="muted">Scope change trend requires computed scope-change history.</p>
            ) : null}

            <div className="chart-section-heading">
              <div>
                <h3>Quality Trend</h3>
                <p className="chart-section-subtitle">
                  Sprint-level quality risk signals over time.
                </p>
              </div>
            </div>
            {!isLoadingSprintConfidence && !sprintConfidenceError && hasQualityCountTrend ? (
              <MetricMultiBarChart
                data={sprintChartRows}
                bars={[
                  { key: "open_high_severity_bugs", label: "High-severity bugs", color: MetricColors.bugs },
                  { key: "bugs_created_during_sprint", label: "Bugs created", color: MetricColors.confidenceWatch },
                ]}
                dataKey="name"
                formatter={formatChartValue}
              />
            ) : null}
            {!isLoadingSprintConfidence && !sprintConfidenceError && hasReopenTrend ? (
              <MetricLineChart
                data={sprintChartRows}
                height={220}
                lines={[
                  {
                    key: "reopen_rate_pct",
                    label: "Reopen events per 100 eligible tickets",
                    color: MetricColors.reopenRate,
                  },
                ]}
                dataKey="name"
                formatter={formatChartValue}
                yDomain={[0, "auto"]}
                yTickFormatter={(value) => `${Math.round(value)}%`}
              />
            ) : null}
            {!isLoadingSprintConfidence && !sprintConfidenceError && !hasQualityCountTrend && !hasReopenTrend ? (
              <p className="muted">Quality trend requires sprint quality history.</p>
            ) : null}

            <div className="chart-section-heading">
              <div>
                <h3>Flow Trend</h3>
                <p className="chart-section-subtitle">
                  Cycle-time history for recent sprints.
                </p>
              </div>
            </div>
            {!isLoadingSprintConfidence && !sprintConfidenceError && hasFlowTrend ? (
              <MetricLineChart
                data={sprintChartRows}
                lines={[
                  {
                    key: "median_cycle_time_days",
                    label: "Median cycle time",
                    color: MetricColors.cycleTime,
                  },
                ]}
                dataKey="name"
                formatter={formatChartValue}
              />
            ) : null}
            {!isLoadingSprintConfidence && !sprintConfidenceError && !hasFlowTrend ? (
              <p className="muted">Flow trend requires cycle-time history.</p>
            ) : null}

            <div className="chart-section-heading">
              <div>
                <h3>Risk Heatmap</h3>
                <p className="chart-section-subtitle">
                  Delivery, quality, flow, and risk status across recent sprints.
                </p>
              </div>
            </div>
            {!isLoadingSprintConfidence && !sprintConfidenceError ? renderRiskHeatmap(sprintChartRows, riskHeatmapCells) : null}

            <div className="chart-section-heading">
              <div>
                <h3>Sprint Evolution Timeline</h3>
                <p className="chart-section-subtitle">
                  Selected sprint events and confidence changes.
                </p>
              </div>
            </div>
            <p className="muted chart-empty-note">Sprint evolution will appear after multiple snapshots are collected.</p>
          </>
        ) : null}
      </section>
      ) : null}

      {mode === "intelligence" ? (
      <section className="panel sprint-controls-panel">
        <div className="panel-heading">
          <h2>Sprint Health Stats</h2>
          <div className="panel-heading-actions">
            <button
              type="button"
              className="secondary-button compact-button"
              aria-expanded={isSprintHealthStatsExpanded}
              onClick={() => setIsSprintHealthStatsExpanded((current) => !current)}
            >
              {isSprintHealthStatsExpanded ? "Minimize" : "Expand"}
            </button>
          </div>
        </div>
        {isSprintHealthStatsExpanded ? (
          <div className="sprint-controls-layout">
            <div className="sprint-control-block">
              <label className="field-label" htmlFor="sprint-selector">
                Select sprint
              </label>
              <select
                id="sprint-selector"
                className="select-input"
                value={selectedScopedSprintId ?? ""}
                disabled={isLoadingList || options.length === 0}
                onChange={(event) => setSelectedSprintId(event.target.value || null)}
              >
                {options.length === 0 ? <option value="">No sprints available</option> : null}
                {options.map((option) => (
                  <option key={option.sprint.sprint_id} value={option.sprint.sprint_id}>
                    {option.label}
                  </option>
                ))}
              </select>
              {selectedSprint ? (
                <dl className="release-health-card-grid" aria-label="Selected sprint summary">
                  <div>
                    <dt>State</dt>
                    <dd>{selectedSprint.state}</dd>
                  </div>
                  <div>
                    <dt>Start Date</dt>
                    <dd>{formatDate(selectedSprint.start_date)}</dd>
                  </div>
                  <div>
                    <dt>End Date</dt>
                    <dd>{formatDate(selectedSprint.end_date)}</dd>
                  </div>
                  <div>
                    <dt>Completed</dt>
                    <dd>{formatDate(selectedSprint.complete_date)}</dd>
                  </div>
                </dl>
              ) : null}
            </div>
            <div className="sprint-control-block sprint-recompute-block">
              <button
                type="button"
                className="primary-button"
                disabled={!selectedScopedSprintId || isRecomputing}
                onClick={handleRecomputeSprint}
              >
                {isRecomputing ? "Recomputing..." : "Recompute Sprint"}
              </button>
              {metrics?.snapshot_age_hours !== null && metrics?.snapshot_age_hours !== undefined ? (
                <p className="muted action-status">Age {metrics.snapshot_age_hours.toFixed(1)}h</p>
              ) : null}
            </div>
          </div>
        ) : null}
      </section>
      ) : null}

      {mode === "intelligence" ? (
      <section className="panel issues-panel">
        <div className="panel-heading">
          <h2>Ticket Situation</h2>
          <div className="panel-heading-actions">
            <span className="muted">{issues.length} shown</span>
            <button
              type="button"
              className="secondary-button compact-button"
              aria-expanded={isTicketSituationExpanded}
              onClick={() => setIsTicketSituationExpanded((current) => !current)}
            >
              {isTicketSituationExpanded ? "Minimize" : "Expand"}
            </button>
          </div>
        </div>
        {isTicketSituationExpanded ? (
          <>
            {!selectedScopedSprintId ? <p className="muted">Select a sprint to view issues.</p> : null}
            {selectedScopedSprintId && !isLoadingDetails && issues.length === 0 ? (
              <p className="muted">No issues linked to this sprint.</p>
            ) : null}
            {issues.length > 0 ? (
              <div className="table-wrapper">
                <table className="issues-table">
                  <thead>
                    <tr>
                      <th>Key</th>
                      <th>Summary</th>
                      <th>Status</th>
                      <th>Priority</th>
                      <th>Story points</th>
                      <th>Initial scope</th>
                      <th>Assignee</th>
                    </tr>
                  </thead>
                  <tbody>
                    {issues.map((issue) => (
                      <tr key={issue.issue_key}>
                        <td>
                          <button type="button" className="link-button" onClick={() => onSelectIssue(issue.issue_key)}>
                            {issue.issue_key}
                          </button>
                        </td>
                        <td>{issue.summary}</td>
                        <td>{issue.status ?? "Unavailable"}</td>
                        <td>{issue.priority ?? "None"}</td>
                        <td>{issue.story_points ?? "None"}</td>
                        <td>{issue.in_initial_scope ? "Yes" : "No"}</td>
                        <td>{issue.assignee ?? "Unassigned"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : null}
          </>
        ) : null}
      </section>
      ) : null}
    </div>
  );
}
