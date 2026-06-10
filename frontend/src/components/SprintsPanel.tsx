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
import {
  calculateExpectedVsActualProgress,
  formatConfidencePercent,
  getBiggestDrag,
  getConfidenceComponentDetails,
  getConfidenceStatus,
  getDeliveryConfidenceSummary,
  getRiskDrivers,
  roundPercent,
} from "./deliveryConfidence";
import {
  buildPredictabilityDisplayModel,
  buildScopeCreepDisplayModel,
  buildSprintWorkStateDisplayModel,
  buildVelocityHealthDisplayModel,
  buildWorkDistributionDisplayModel,
  formatPercent,
  generateFocusAreas,
  getGroupSummary,
  getMetricStatus,
  type MetricEvaluation,
} from "./sprintMetrics";

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

const sprintMetricInfoText: Record<keyof SprintMetricValues, string> = {
  committed_scope: "Issues explicitly linked to this sprint.",
  completed_scope_pct: "Shows how much committed work is already done.",
  open_blockers: "Open blockers can stop delivery and should be cleared quickly.",
  open_high_severity_bugs: "Open high-severity bugs indicate quality risk inside the sprint.",
  bugs_created_during_sprint: "New bugs created during the sprint can displace planned work.",
  in_progress_count: "Active work currently moving through the sprint.",
  not_started_count: "Committed work that has not started yet.",
  rollover_count: "Work that did not finish by sprint close.",
  median_cycle_time_days: "Typical time from active work start to done.",
  reopen_rate_pct: "Reopened work signals quality or acceptance churn.",
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
  if (metricName === "completed_scope_pct" || metricName === "reopen_rate_pct") {
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
    return `${formatPercent(value)} of committed scope is done`;
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
    return value === 0 ? "No reopened work" : `${formatPercent(value)} of sprint work reopened`;
  }
  if (metricName === "rollover_count") {
    return value === 0 ? "No rollover" : `${value} issues rolled over`;
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
    focusMessage = `Rollover is ${formattedValue}.`;
  } else if (metricName === "reopen_rate_pct") {
    focusMessage = `Reopen rate is ${formattedValue}.`;
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
  const componentDetails = getConfidenceComponentDetails(confidence.components);
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
      <section className="confidence-section">
        <div className="confidence-section-heading">
          <h3>Confidence Breakdown</h3>
        </div>
        <div className="confidence-breakdown-grid">
          {componentDetails.map((component) => (
            <article className={`metric-card confidence-component status-${component.status.level}`} key={component.key}>
              <div className="confidence-component-heading">
                <h4>{component.label}</h4>
                <span className={`confidence-status-pill confidence-status-${component.status.level}`}>
                  {component.status.label}
                </span>
              </div>
              <strong className={`confidence-status-text-${component.status.level}`}>
                {formatConfidencePercent(component.score)}
              </strong>
              <p>{component.explanation}</p>
            </article>
          ))}
        </div>
      </section>

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
          <dt>Committed scope</dt>
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
  const predictabilityCard = useMemo(
    () => buildPredictabilityDisplayModel(sprintCommitmentReliabilityRows),
    [sprintCommitmentReliabilityRows]
  );
  const workDistributionCard = useMemo(() => buildWorkDistributionDisplayModel(issues), [issues]);
  const sprintWorkStateCard = useMemo(
    () => (metrics ? buildSprintWorkStateDisplayModel(metrics.metrics, issues) : null),
    [metrics, issues]
  );
  const scopeCreepCard = useMemo(
    () => (metrics?.delivery_confidence ? buildScopeCreepDisplayModel(metrics.delivery_confidence) : null),
    [metrics?.delivery_confidence]
  );
  const velocityHealthCard = useMemo(
    () => (metrics?.delivery_confidence ? buildVelocityHealthDisplayModel(metrics.delivery_confidence) : null),
    [metrics?.delivery_confidence]
  );
  const deliveryConfidenceStatus = metrics?.delivery_confidence
    ? getConfidenceStatus(metrics.delivery_confidence.score)
    : null;
  const metricEvaluations = useMemo(() => {
    if (!metrics) {
      return [];
    }
    const evaluations: MetricEvaluation[] = [];
    if (scopeCreepCard) {
      const value = metrics.delivery_confidence?.inputs.scope_stability_index === null || !metrics.delivery_confidence
        ? null
        : Number((metrics.delivery_confidence.inputs.scope_stability_index * 100).toFixed(2));
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
      const average = metrics.delivery_confidence?.inputs.historical_velocity;
      const completed = metrics.delivery_confidence?.inputs.completed_effective_points;
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
  }, [metrics, predictabilityCard, scopeCreepCard, velocityHealthCard, workDistributionCard]);
  const focusAreas = useMemo(() => generateFocusAreas(metricEvaluations), [metricEvaluations]);

  function renderSprintMetricCard(metricName: keyof SprintMetricValues) {
    if (!metrics || metricName === "delivery_confidence_score") {
      return null;
    }
    const value = metrics.metrics[metricName];
    const status = getMetricStatus(metricName, value);
    return (
      <MetricStatusCard
        key={metricName}
        title={sprintMetricLabels[metricName]}
        value={formatMetricValue(metricName, value)}
        status={status}
        comparison={getMetricContext(metricName, metrics, metrics.delivery_confidence)}
        comparisonImpact={getMetricImpact(status)}
        infoText={sprintMetricInfoText[metricName]}
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
            {metrics?.delivery_confidence && deliveryConfidenceStatus ? (
              <div className="delivery-confidence-decision" aria-label={`Delivery confidence ${formatConfidencePercent(metrics.delivery_confidence.score)}, ${deliveryConfidenceStatus.label}`}>
                <strong className={`delivery-confidence-score confidence-status-text-${deliveryConfidenceStatus.level}`}>
                  {formatConfidencePercent(metrics.delivery_confidence.score)}
                </strong>
                <span className={`confidence-status-pill confidence-status-${deliveryConfidenceStatus.level}`}>
                  {deliveryConfidenceStatus.label}
                </span>
              </div>
            ) : null}
          </div>
          <div className="panel-heading-actions">
            {metrics?.delivery_confidence ? (
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
        {!isLoadingDetails && metrics?.delivery_confidence ? (
          <p className="delivery-confidence-summary">
            {getDeliveryConfidenceSummary(metrics.delivery_confidence.components)}
          </p>
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
                <section className="focus-areas-section">
                  <h3>Focus Areas</h3>
                  <ol className="focus-area-list">
                    {focusAreas.map((area) => (
                      <li key={area}>{area}</li>
                    ))}
                  </ol>
                </section>
                <MetricCategorySection title="Delivery" summary={getGroupSummary("delivery", metricEvaluations)}>
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
                  <MetricStatusCard
                    title="Team predictability"
                    value={predictabilityCard.value}
                    status={predictabilityCard.status}
                    comparison={predictabilityCard.comparison}
                    comparisonImpact={predictabilityCard.impact}
                    details={predictabilityCard.details}
                    infoText="Shows how reliably recent closed sprints completed committed work."
                  />
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
                      infoText="Condenses committed, active, not-started, done, and rollover work into one scan-friendly card."
                    />
                  </MetricCategorySection>
                ) : null}
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
