import { useEffect, useMemo, useState } from "react";
import { apiClient } from "../api/client";
import type {
  DeliveryConfidenceDetail,
  Sprint,
  SprintIssue,
  SprintMetricValues,
  SprintMetricsResponse,
} from "../api/types";
import {
  MetricColors,
  MetricLineChart,
  MetricBarChart,
  MetricMultiBarChart,
  formatDecimal,
} from "./ChartComponents";
import {
  MetricCategorySection,
  MetricStatusCard,
  type MetricImpact,
  type MetricStatus,
} from "./MetricCards";

type SprintOption = {
  label: string;
  sprint: Sprint;
};

type SprintStoryPointRow = {
  sprint_id: string;
  name: string;
  story_points: number;
  is_not_closed: boolean;
};

type SprintConfidenceRow = {
  sprint_id: string;
  name: string;
  delivery_confidence: number;
  is_not_closed: boolean;
};

type SprintCommitmentReliabilityRow = {
  sprint_id: string;
  name: string;
  committed_story_points: number;
  completed_story_points: number;
  is_not_closed: boolean;
};

type SprintMetricHistoryRow = {
  confidence: SprintConfidenceRow;
  commitmentReliability: SprintCommitmentReliabilityRow;
};

type ConfidenceTrend = "increasing" | "decreasing" | "similar";

const sprintIssuePageSize = 100;
const committedStoryPointColor = MetricColors.committedScope;
const completedStoryPointColor = MetricColors.completedScope;

const sprintMetricLabels: Record<keyof SprintMetricValues, string> = {
  committed_scope: "Committed scope",
  completed_scope_pct: "Completed scope",
  open_blockers: "Open blockers",
  open_high_severity_bugs: "Open high-severity bugs",
  bugs_created_during_sprint: "Bugs created during sprint",
  in_progress_count: "In progress",
  not_started_count: "Not started",
  rollover_count: "Rollover",
  median_cycle_time_days: "Median cycle time",
  reopen_rate_pct: "Reopen rate",
  delivery_confidence_score: "Delivery confidence",
};

const sprintMetricDescriptions: Record<keyof SprintMetricValues, string> = {
  committed_scope: "Issues explicitly linked to this sprint.",
  completed_scope_pct: "Done issues divided by total sprint issues.",
  open_blockers: "Sprint issues excluded from done status and classified as blockers by issue type (Blocker/Incident), priority (Blocker/Highest/Critical), status (Blocked), or the configured blocker field.",
  open_high_severity_bugs: "Open sprint bugs with high or critical priority.",
  bugs_created_during_sprint: "Sprint bugs created between the sprint start and the current sprint window end.",
  in_progress_count: "Sprint issues currently in active work status: In Progress, In Development, In Review, or In Testing.",
  not_started_count: "Sprint issues that are neither in progress nor done.",
  rollover_count: "Closed-sprint issues that did not reach done.",
  median_cycle_time_days: "Median days from first in-progress to first done.",
  reopen_rate_pct: "Sprint issues that moved from done back to active work.",
  delivery_confidence_score: "Composite score from progress, velocity, blockers, and scope stability.",
};

const confidenceComponentLabels: Record<keyof DeliveryConfidenceDetail["components"], string> = {
  progress_alignment: "Progress alignment",
  velocity_fit: "Velocity fit",
  blocker_penalty: "Blocker penalty",
  scope_stability: "Scope stability",
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
  if (metricName === "completed_scope_pct" || metricName === "reopen_rate_pct") {
    return `${value.toFixed(2)}%`;
  }
  return value.toFixed(2);
}

function formatNullableNumber(value: number | null | undefined, suffix = "") {
  if (value === null || value === undefined) {
    return "N/A";
  }
  return `${value.toFixed(2)}${suffix}`;
}

function getProgressAlignmentClass(value: number) {
  if (value === 100) {
    return "confidence-value-perfect";
  }
  if (value >= 76) {
    return "confidence-value-good";
  }
  if (value >= 36) {
    return "confidence-value-warning";
  }
  return "confidence-value-danger";
}

function getVelocityFitClass(value: number) {
  if (value === 50) {
    return "confidence-value-neutral";
  }
  if (value > 50) {
    return "confidence-value-success";
  }
  return "confidence-value-danger";
}

function getBlockerPenaltyClass(value: number) {
  if (value >= 80) {
    return "confidence-value-success";
  }
  if (value >= 60) {
    return "confidence-value-warning";
  }
  return "confidence-value-danger";
}

function getDeliveryConfidenceClass(value: number) {
  if (value > 80) {
    return "confidence-value-success";
  }
  if (value >= 55) {
    return "confidence-value-warning";
  }
  return "confidence-value-danger";
}

function getScopeStabilityClass(value: number) {
  if (value >= 80) {
    return "confidence-value-success";
  }
  if (value >= 50) {
    return "confidence-value-warning";
  }
  return "confidence-value-danger";
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
  onSelectIssue: (issueKey: string) => void
) {
  if (issueKeys.length === 0) {
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

function getConfidenceTrend(rows: SprintConfidenceRow[]): ConfidenceTrend | null {
  const latestValues = rows.slice(-3).map((row) => row.delivery_confidence);
  if (latestValues.length < 2) {
    return null;
  }

  const difference = latestValues[latestValues.length - 1] - latestValues[0];
  if (difference > 1) {
    return "increasing";
  }
  if (difference < -1) {
    return "decreasing";
  }
  return "similar";
}

function getConfidenceTrendTooltip(trend: ConfidenceTrend) {
  return `Based on the last 3 sprints, confidence is ${trend}.`;
}

function renderDeliveryConfidence(confidence: DeliveryConfidenceDetail) {
  return (
    <div className="metric-grid confidence-grid">
      <div className="confidence-breakdown">
        {(Object.keys(confidence.components) as Array<keyof DeliveryConfidenceDetail["components"]>).map((key) => {
          const value = confidence.components[key];
          return (
            <article className="metric-card confidence-component" key={key}>
              <h3>
                {confidenceComponentLabels[key]}
                {key === "progress_alignment" ? (
                  <button
                    type="button"
                    className="info-button"
                    title="Progress alignment compares percent completed versus percent of sprint time elapsed. Closer to 100 means the sprint is on pace."
                    aria-label="Progress alignment info"
                  >
                    i
                  </button>
                ) : null}
                {key === "velocity_fit" ? (
                  <button
                    type="button"
                    className="info-button"
                    title="Velocity fit compares remaining work to estimated remaining capacity.\n\nUnder 50 means capacity is weak and lowers the overall score. Over 50 means capacity is stronger and raises the score. Exactly 50 is the fallback/neutral baseline contribution in the formula."
                    aria-label="Velocity fit info"
                  >
                    i
                  </button>
                ) : null}
                {key === "blocker_penalty" ? (
                  <button
                    type="button"
                    className="info-button"
                    title="Blocker penalty rewards sprints with fewer blocked issues. 80-100 is good (few or no blockers), 60-79 is moderate, and 0-59 is poor.\n\nA lower blocker penalty reduces the overall delivery confidence score."
                    aria-label="Blocker penalty info"
                  >
                    i
                  </button>
                ) : null}
                {key === "scope_stability" ? (
                  <button
                    type="button"
                    className="info-button"
                    title="Scope stability measures post-start scope churn. 80-100 is good, 50-79 is moderate, and 0-49 is poor.\n\nMore scope changes after sprint start reduce the overall delivery confidence score."
                    aria-label="Scope stability info"
                  >
                    i
                  </button>
                ) : null}
              </h3>
              <strong
                className={
                  key === "progress_alignment"
                    ? getProgressAlignmentClass(value)
                    : key === "velocity_fit"
                    ? getVelocityFitClass(value)
                    : key === "blocker_penalty"
                    ? getBlockerPenaltyClass(value)
                    : key === "scope_stability"
                    ? getScopeStabilityClass(value)
                    : undefined
                }
              >
                {value.toFixed(2)}
              </strong>
            </article>
          );
        })}
      </div>
      <article className="metric-card confidence-input-card">
        <h3>Calculation inputs</h3>
        <dl className="confidence-inputs">
          <dt>Committed pts</dt>
          <dd>{confidence.inputs.committed_effective_points.toFixed(2)}</dd>
          <dt>Completed pts</dt>
          <dd>{confidence.inputs.completed_effective_points.toFixed(2)}</dd>
          <dt>Remaining pts</dt>
          <dd>{confidence.inputs.remaining_effective_points.toFixed(2)}</dd>
          <dt>Elapsed</dt>
          <dd>{formatNullableNumber(confidence.inputs.time_elapsed_pct, "%")}</dd>
          <dt>Velocity</dt>
          <dd>{formatNullableNumber(confidence.inputs.historical_velocity)}</dd>
          <dt>Baseline</dt>
          <dd>{confidence.inputs.baseline_sprint_count}</dd>
          <dt>Blocked ratio</dt>
          <dd>{confidence.inputs.blocked_issue_ratio.toFixed(4)}</dd>
          <dt>Scope changes</dt>
          <dd>{confidence.inputs.scope_change_count}</dd>
        </dl>
      </article>
    </div>
  );
}

function formatDate(value: string | null) {
  if (!value) {
    return "N/A";
  }
  return new Date(value).toLocaleDateString();
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

function getRatioStatus(value: number | null): MetricStatus {
  if (value === null) {
    return "neutral";
  }
  if (value >= 90) {
    return "good";
  }
  return value >= 75 ? "warning" : "critical";
}

function getSprintMetricStatus(metricName: keyof SprintMetricValues, value: number | null): MetricStatus {
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

function buildSprintMetricComparison(metricName: keyof SprintMetricValues, value: number | null): {
  text: string;
  impact: MetricImpact;
} {
  if (value === null) {
    return { text: "Current snapshot unavailable", impact: "unknown" };
  }
  if (metricName === "open_blockers" || metricName === "open_high_severity_bugs") {
    return value === 0
      ? { text: "No open risk tickets", impact: "positive" }
      : { text: "Open risk tickets need attention", impact: "negative" };
  }
  if (metricName === "completed_scope_pct") {
    return { text: `${value.toFixed(0)}% of committed scope is done`, impact: value >= 80 ? "positive" : "neutral" };
  }
  if (metricName === "rollover_count") {
    return value === 0
      ? { text: "No rollover in this snapshot", impact: "positive" }
      : { text: `${value} issues did not finish`, impact: "negative" };
  }
  if (metricName === "bugs_created_during_sprint") {
    return value === 0
      ? { text: "No sprint-created bugs", impact: "positive" }
      : { text: `${value} bugs created in sprint window`, impact: "negative" };
  }
  return { text: "Current sprint snapshot", impact: "neutral" };
}

function buildScopeCreepCard(confidence: DeliveryConfidenceDetail) {
  const index = confidence.inputs.scope_stability_index;
  const creepPct = index === null ? null : Number((index * 100).toFixed(2));
  const status: MetricStatus = creepPct === null ? "neutral" : creepPct > 20 ? "critical" : creepPct > 10 ? "warning" : "good";
  return {
    value: creepPct === null ? "N/A" : `${creepPct.toFixed(2)}%`,
    status,
    comparison:
      confidence.inputs.scope_change_count === 0
        ? "No changes after sprint start"
        : `${confidence.inputs.scope_change_count} changes after sprint start`,
    impact: confidence.inputs.scope_change_count === 0 ? ("positive" as MetricImpact) : ("negative" as MetricImpact),
    details: [
      `${confidence.inputs.scope_added_count} issues added`,
      `${confidence.inputs.scope_removed_count} issues removed`,
    ],
  };
}

function buildVelocityHealthCard(confidence: DeliveryConfidenceDetail) {
  const current = confidence.inputs.completed_effective_points;
  const average = confidence.inputs.historical_velocity;
  const pct = average && average > 0 ? Number(((current / average) * 100).toFixed(0)) : null;
  return {
    value: pct === null ? "N/A" : `${pct}% of normal`,
    status: getRatioStatus(pct),
    comparison:
      average === null
        ? "Baseline unavailable"
        : `Current ${current.toFixed(2)} SP vs average ${average.toFixed(2)} SP`,
    impact: pct === null ? ("unknown" as MetricImpact) : pct >= 90 ? ("positive" as MetricImpact) : ("negative" as MetricImpact),
  };
}

function buildPredictabilityCard(rows: SprintCommitmentReliabilityRow[]) {
  const closedRows = rows.filter((row) => !row.is_not_closed && row.committed_story_points > 0);
  if (closedRows.length === 0) {
    return {
      value: "N/A",
      status: "neutral" as MetricStatus,
      comparison: "Closed sprint baseline unavailable",
      impact: "unknown" as MetricImpact,
    };
  }
  const ratios = closedRows.map((row) => row.completed_story_points / row.committed_story_points);
  const pct = Number(((ratios.reduce((sum, value) => sum + value, 0) / ratios.length) * 100).toFixed(0));
  return {
    value: `${pct}%`,
    status: getRatioStatus(pct),
    comparison: `Average across last ${closedRows.length} closed sprints`,
    impact: pct >= 90 ? ("positive" as MetricImpact) : pct >= 75 ? ("neutral" as MetricImpact) : ("negative" as MetricImpact),
  };
}

function effectiveIssuePoints(issue: SprintIssue) {
  return issue.story_points !== null && issue.story_points !== undefined && issue.story_points >= 0 ? issue.story_points : 1;
}

function buildWorkDistributionCard(issues: SprintIssue[]) {
  if (issues.length === 0) {
    return {
      value: "N/A",
      status: "neutral" as MetricStatus,
      comparison: "No sprint work in this snapshot",
      impact: "unknown" as MetricImpact,
      details: [],
    };
  }

  const totals = new Map<string, number>();
  for (const issue of issues) {
    const assignee = issue.assignee?.trim() || "Unassigned";
    totals.set(assignee, (totals.get(assignee) ?? 0) + effectiveIssuePoints(issue));
  }
  const totalPoints = Array.from(totals.values()).reduce((sum, value) => sum + value, 0);
  const rows = Array.from(totals.entries())
    .map(([assignee, points]) => ({
      assignee,
      points,
      pct: totalPoints === 0 ? 0 : Number(((points / totalPoints) * 100).toFixed(0)),
    }))
    .sort((left, right) => right.points - left.points || left.assignee.localeCompare(right.assignee));
  const top = rows[0];
  const status: MetricStatus = top.pct > 50 ? "critical" : top.pct > 35 ? "warning" : "good";
  return {
    value: `${top.pct}% top load`,
    status,
    comparison: `${top.assignee} owns ${top.pct}% of current work`,
    impact: status === "good" ? ("positive" as MetricImpact) : ("negative" as MetricImpact),
    details: rows.slice(0, 4).map((row) => `${row.assignee} ${row.pct}%`),
  };
}

interface SprintsPanelProps {
  refreshNonce: number;
  onSelectIssue: (issueKey: string) => void;
}

export function SprintsPanel({ refreshNonce, onSelectIssue }: SprintsPanelProps) {
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
  const [sprintStoryPointRows, setSprintStoryPointRows] = useState<SprintStoryPointRow[]>([]);
  const [isLoadingSprintStoryPoints, setIsLoadingSprintStoryPoints] = useState(false);
  const [sprintStoryPointError, setSprintStoryPointError] = useState<string | null>(null);
  const [sprintConfidenceRows, setSprintConfidenceRows] = useState<SprintConfidenceRow[]>([]);
  const [sprintCommitmentReliabilityRows, setSprintCommitmentReliabilityRows] = useState<
    SprintCommitmentReliabilityRow[]
  >([]);
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

  const options = useMemo(() => buildOptions(currentSprint, closedSprints), [currentSprint, closedSprints]);
  const selectedSprint = options.find((option) => option.sprint.sprint_id === selectedSprintId)?.sprint ?? null;
  const recentSprints = useMemo(() => {
    const sprintsById = new Map<string, Sprint>();
    if (currentSprint) {
      sprintsById.set(currentSprint.sprint_id, currentSprint);
    }
    for (const sprint of closedSprints) {
      sprintsById.set(sprint.sprint_id, sprint);
    }
    return getRecentSprints(Array.from(sprintsById.values()));
  }, [currentSprint, closedSprints]);
  const confidenceTrend = useMemo(() => getConfidenceTrend(sprintConfidenceRows), [sprintConfidenceRows]);
  const confidenceTrendTooltip = confidenceTrend ? getConfidenceTrendTooltip(confidenceTrend) : null;
  const predictabilityCard = useMemo(
    () => buildPredictabilityCard(sprintCommitmentReliabilityRows),
    [sprintCommitmentReliabilityRows]
  );
  const workDistributionCard = useMemo(() => buildWorkDistributionCard(issues), [issues]);

  function renderSprintMetricCard(metricName: keyof SprintMetricValues) {
    if (!metrics || metricName === "delivery_confidence_score") {
      return null;
    }
    const value = metrics.metrics[metricName];
    const comparison = buildSprintMetricComparison(metricName, value);
    return (
      <MetricStatusCard
        key={metricName}
        title={sprintMetricLabels[metricName]}
        value={formatMetricValue(metricName, value)}
        status={getSprintMetricStatus(metricName, value)}
        comparison={comparison.text}
        comparisonImpact={comparison.impact}
      >
        {renderMetricIssueKeys(metricName, value, metrics, issuesByKey, onSelectIssue)}
      </MetricStatusCard>
    );
  }

  useEffect(() => {
    let isActive = true;

    async function loadSprintList() {
      setIsLoadingList(true);
      setErrorMessage(null);
      try {
        const [currentResult, closedResult] = await Promise.allSettled([
          apiClient.getCurrentSprint(),
          apiClient.getClosedSprints(),
        ]);
        if (!isActive) {
          return;
        }
        const activeSprint = currentResult.status === "fulfilled" ? currentResult.value.item : null;
        const closed = closedResult.status === "fulfilled" ? closedResult.value.items : [];
        setCurrentSprint(activeSprint);
        setClosedSprints(closed);
        setSelectedSprintId((existing) => existing ?? activeSprint?.sprint_id ?? closed[0]?.sprint_id ?? null);
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
  }, [refreshNonce]);

  useEffect(() => {
    if (!selectedSprintId) {
      setMetrics(null);
      setIssues([]);
      return;
    }

    const sprintId = selectedSprintId;
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
  }, [selectedSprintId]);

  useEffect(() => {
    if (recentSprints.length === 0) {
      setSprintStoryPointRows([]);
      return;
    }

    let isActive = true;

    async function loadSprintStoryPoints() {
      setIsLoadingSprintStoryPoints(true);
      setSprintStoryPointError(null);
      try {
        const rows = await Promise.all(
          recentSprints.map(async (sprint) => {
            let storyPoints = 0;
            let fetchedCount = 0;
            let total = 0;

            while (true) {
              const response = await apiClient.getSprintIssues(sprint.sprint_id, fetchedCount, sprintIssuePageSize);
              total = response.total;
              for (const issue of response.items) {
                storyPoints += issue.story_points ?? 0;
              }

              fetchedCount += response.items.length;
              if (fetchedCount >= total || response.items.length === 0) {
                break;
              }
            }

            return {
              sprint_id: sprint.sprint_id,
              name: sprint.name,
              story_points: Number(storyPoints.toFixed(2)),
              is_not_closed: isNotClosedSprint(sprint),
            };
          })
        );

        if (isActive) {
          setSprintStoryPointRows(rows);
        }
      } catch (error) {
        if (isActive) {
          setSprintStoryPointError(error instanceof Error ? error.message : "Failed to load sprint story points.");
        }
      } finally {
        if (isActive) {
          setIsLoadingSprintStoryPoints(false);
        }
      }
    }

    void loadSprintStoryPoints();

    return () => {
      isActive = false;
    };
  }, [recentSprints, refreshNonce]);

  useEffect(() => {
    if (recentSprints.length === 0) {
      setSprintConfidenceRows([]);
      setSprintCommitmentReliabilityRows([]);
      return;
    }

    let isActive = true;

    async function loadSprintConfidence() {
      setIsLoadingSprintConfidence(true);
      setSprintConfidenceError(null);
      try {
        const results = await Promise.all(
          recentSprints.map(async (sprint) => {
            const response = await apiClient.getSprintMetrics(sprint.sprint_id);
            if (!response.is_computed || !response.delivery_confidence) {
              return null;
            }
            const deliveryConfidence = response.delivery_confidence;
            return {
              confidence: {
                sprint_id: sprint.sprint_id,
                name: sprint.name,
                delivery_confidence: Number(deliveryConfidence.score.toFixed(2)),
                is_not_closed: isNotClosedSprint(sprint),
              },
              commitmentReliability: {
                sprint_id: sprint.sprint_id,
                name: sprint.name,
                committed_story_points: Number(deliveryConfidence.inputs.committed_effective_points.toFixed(2)),
                completed_story_points: Number(deliveryConfidence.inputs.completed_effective_points.toFixed(2)),
                is_not_closed: isNotClosedSprint(sprint),
              },
            };
          })
        );

        if (isActive) {
          const metricHistoryRows = results.filter((row): row is SprintMetricHistoryRow => row !== null);
          setSprintConfidenceRows(metricHistoryRows.map((row) => row.confidence));
          setSprintCommitmentReliabilityRows(metricHistoryRows.map((row) => row.commitmentReliability));
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
  }, [recentSprints, refreshNonce]);

  async function handleRecomputeSprint() {
    if (!selectedSprintId || isRecomputing) {
      return;
    }
    setIsRecomputing(true);
    setErrorMessage(null);
    try {
      await apiClient.recomputeSprint(selectedSprintId);
      const [metricsResponse, issueResponse] = await Promise.all([
        apiClient.getSprintMetrics(selectedSprintId),
        loadAllSprintIssues(selectedSprintId),
      ]);
      setMetrics(metricsResponse);
      setIssues(issueResponse);
      const recomputedConfidence = metricsResponse.delivery_confidence;
      if (recomputedConfidence) {
        setSprintConfidenceRows((currentRows) =>
          currentRows.map((row) =>
            row.sprint_id === selectedSprintId
              ? { ...row, delivery_confidence: Number(recomputedConfidence.score.toFixed(2)) }
              : row
          )
        );
        setSprintCommitmentReliabilityRows((currentRows) =>
          currentRows.map((row) =>
            row.sprint_id === selectedSprintId
              ? {
                  ...row,
                  committed_story_points: Number(recomputedConfidence.inputs.committed_effective_points.toFixed(2)),
                  completed_story_points: Number(recomputedConfidence.inputs.completed_effective_points.toFixed(2)),
                }
              : row
          )
        );
      }
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : "Failed to recompute sprint metrics.");
    } finally {
      setIsRecomputing(false);
    }
  }

  return (
    <div className="sprints-panel">
      {errorMessage ? <div className="panel error-panel">{errorMessage}</div> : null}

      <section className="panel delivery-confidence-panel">
        <div className="panel-heading">
          <h2 className="delivery-confidence-title">
            Delivery Confidence
            <button
              type="button"
              className="info-button"
              title="Delivery confidence is a weighted sprint health score. It combines progress alignment, velocity fit, blocker penalty, and scope stability to produce a single confidence value."
              aria-label="Delivery confidence info"
            >
              i
            </button>
          </h2>
          <div className="panel-heading-actions">
            {metrics?.delivery_confidence ? (
              <>
                <div className="confidence-score-value delivery-confidence-heading-score">
                  <strong className={getDeliveryConfidenceClass(metrics.delivery_confidence.score)}>
                    {metrics.delivery_confidence.score.toFixed(2)}
                  </strong>
                  {confidenceTrend && confidenceTrendTooltip ? (
                    <span
                      className={`confidence-trend-icon ${confidenceTrend}`}
                      title={confidenceTrendTooltip}
                      aria-label={confidenceTrendTooltip}
                      role="img"
                      tabIndex={0}
                    />
                  ) : null}
                </div>
                <button
                  type="button"
                  className="secondary-button compact-button"
                  aria-expanded={isDeliveryConfidenceExpanded}
                  onClick={() => setIsDeliveryConfidenceExpanded((c) => !c)}
                >
                  {isDeliveryConfidenceExpanded ? "Minimize" : "Expand"}
                </button>
              </>
            ) : null}
          </div>
        </div>
        {isLoadingDetails ? <p className="muted">Loading delivery confidence...</p> : null}
        {!isLoadingDetails && metrics && !metrics.is_computed ? (
          <p className="muted">Sprint metrics have not been computed yet.</p>
        ) : null}
        {!isLoadingDetails && metrics?.delivery_confidence && isDeliveryConfidenceExpanded
          ? renderDeliveryConfidence(metrics.delivery_confidence)
          : null}
      </section>

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
                <MetricCategorySection title="Delivery">
                  {renderSprintMetricCard("completed_scope_pct")}
                  {metrics.delivery_confidence ? (
                    <MetricStatusCard
                      title="Scope creep"
                      value={buildScopeCreepCard(metrics.delivery_confidence).value}
                      status={buildScopeCreepCard(metrics.delivery_confidence).status}
                      comparison={buildScopeCreepCard(metrics.delivery_confidence).comparison}
                      comparisonImpact={buildScopeCreepCard(metrics.delivery_confidence).impact}
                      details={buildScopeCreepCard(metrics.delivery_confidence).details}
                    >
                      {renderScopeIssueKeys(
                        "Scope change tickets",
                        metrics.delivery_confidence.inputs.scope_change_issue_keys ?? [],
                        issuesByKey,
                        onSelectIssue
                      )}
                    </MetricStatusCard>
                  ) : null}
                  {metrics.delivery_confidence ? (
                    <MetricStatusCard
                      title="Velocity health"
                      value={buildVelocityHealthCard(metrics.delivery_confidence).value}
                      status={buildVelocityHealthCard(metrics.delivery_confidence).status}
                      comparison={buildVelocityHealthCard(metrics.delivery_confidence).comparison}
                      comparisonImpact={buildVelocityHealthCard(metrics.delivery_confidence).impact}
                    />
                  ) : null}
                  <MetricStatusCard
                    title="Team predictability"
                    value={predictabilityCard.value}
                    status={predictabilityCard.status}
                    comparison={predictabilityCard.comparison}
                    comparisonImpact={predictabilityCard.impact}
                  />
                  {renderSprintMetricCard("committed_scope")}
                </MetricCategorySection>
                <MetricCategorySection title="Quality">
                  {renderSprintMetricCard("open_high_severity_bugs")}
                  {renderSprintMetricCard("bugs_created_during_sprint")}
                  {renderSprintMetricCard("reopen_rate_pct")}
                </MetricCategorySection>
                <MetricCategorySection title="Flow">
                  {renderSprintMetricCard("median_cycle_time_days")}
                  {renderSprintMetricCard("in_progress_count")}
                  {renderSprintMetricCard("not_started_count")}
                </MetricCategorySection>
                <MetricCategorySection title="Risk">
                  {renderSprintMetricCard("open_blockers")}
                  {renderSprintMetricCard("rollover_count")}
                  <MetricStatusCard
                    title="Work distribution"
                    value={workDistributionCard.value}
                    status={workDistributionCard.status}
                    comparison={workDistributionCard.comparison}
                    comparisonImpact={workDistributionCard.impact}
                    details={workDistributionCard.details}
                  />
                </MetricCategorySection>
              </div>
            ) : null}
          </>
        ) : null}
      </section>

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
            {!selectedSprintId ? <p className="muted">Select a sprint to view issues.</p> : null}
            {selectedSprintId && !isLoadingDetails && issues.length === 0 ? (
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
                        <td>{issue.status}</td>
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
            <div id="delivery-confidence-history" className="chart-section-heading first">
              <h3>Delivery confidence in recent sprints</h3>
              {sprintConfidenceRows.length > 0 ? (
                <span className="muted">Last {sprintConfidenceRows.length}</span>
              ) : null}
            </div>
            {isLoadingSprintConfidence ? <p className="muted">Loading delivery confidence...</p> : null}
            {sprintConfidenceError ? <p className="error-text">{sprintConfidenceError}</p> : null}
            {!isLoadingSprintConfidence && !sprintConfidenceError && sprintConfidenceRows.length === 0 ? (
              <p className="muted">No sprint confidence data available yet.</p>
            ) : null}
            {!isLoadingSprintConfidence && !sprintConfidenceError && sprintConfidenceRows.length > 0 ? (
              <MetricLineChart
                data={sprintConfidenceRows}
                lines={[
                  {
                    key: "delivery_confidence",
                    label: "Delivery confidence",
                    color: MetricColors.sprintConfidence,
                  },
                ]}
                dataKey="name"
                formatter={formatDecimal}
                yDomain={[0, 100]}
                yTickFormatter={(value) => String(Math.round(value))}
              />
            ) : null}

            <div className="chart-section-heading">
              <h3>Sprint Commitment Reliability</h3>
              {sprintCommitmentReliabilityRows.length > 0 ? (
                <span className="muted">Last {sprintCommitmentReliabilityRows.length}</span>
              ) : null}
            </div>
            {isLoadingSprintConfidence ? <p className="muted">Loading sprint commitment reliability...</p> : null}
            {sprintConfidenceError ? <p className="error-text">{sprintConfidenceError}</p> : null}
            {!isLoadingSprintConfidence && !sprintConfidenceError && sprintCommitmentReliabilityRows.length === 0 ? (
              <p className="muted">No sprint commitment reliability data available yet.</p>
            ) : null}
            {!isLoadingSprintConfidence && !sprintConfidenceError && sprintCommitmentReliabilityRows.length > 0 ? (
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
                formatter={(value) => String(value)}
              />
            ) : null}

            <div className="chart-section-heading">
              <h3>Story points in every sprint</h3>
              {sprintStoryPointRows.length > 0 ? (
                <span className="muted">Last {sprintStoryPointRows.length}</span>
              ) : null}
            </div>
            <div className="chart-legend-note" aria-label="Sprint state color legend">
              <span className="chart-legend-swatch not-closed" aria-hidden="true" />
              <span>All sprints in this color are not closed yet.</span>
            </div>
            {sprintStoryPointError ? <p className="error-text">{sprintStoryPointError}</p> : null}
            {!isLoadingSprintStoryPoints && !sprintStoryPointError ? (
              <MetricBarChart
                data={sprintStoryPointRows}
                barKey="story_points"
                barLabel="Story points"
                barColor={MetricColors.closedSprintStoryPoints}
                cellColors={(row) => {
                  const sprintRow = row as SprintStoryPointRow;
                  return sprintRow.is_not_closed
                    ? MetricColors.notClosedSprintStoryPoints
                    : MetricColors.closedSprintStoryPoints;
                }}
                loading={isLoadingSprintStoryPoints}
                empty={sprintStoryPointRows.length === 0}
                emptyMessage="No sprint story point data available yet."
              />
            ) : null}
          </>
        ) : null}
      </section>

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
                value={selectedSprintId ?? ""}
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
                <div className="sprint-meta">
                  <p>
                    <strong>State:</strong> {selectedSprint.state}
                  </p>
                  <p>
                    <strong>Start:</strong> {formatDate(selectedSprint.start_date)}
                  </p>
                  <p>
                    <strong>End:</strong> {formatDate(selectedSprint.end_date)}
                  </p>
                  <p>
                    <strong>Completed:</strong> {formatDate(selectedSprint.complete_date)}
                  </p>
                </div>
              ) : null}
            </div>
            <div className="sprint-control-block sprint-recompute-block">
              <button
                type="button"
                className="primary-button"
                disabled={!selectedSprintId || isRecomputing}
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
    </div>
  );
}
