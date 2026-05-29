import { useEffect, useMemo, useState } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { apiClient } from "../api/client";
import type {
  DeliveryConfidenceDetail,
  Sprint,
  SprintIssue,
  SprintMetricValues,
  SprintMetricsResponse,
} from "../api/types";

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

type ConfidenceTrend = "increasing" | "decreasing" | "similar";

const sprintIssuePageSize = 100;
const closedSprintStoryPointColor = "#0b6bcb";
const notClosedSprintStoryPointColor = "#e48f00";
const sprintConfidenceColor = "#237445";

const sprintMetricLabels: Record<keyof SprintMetricValues, string> = {
  committed_scope: "Committed scope",
  completed_scope_pct: "Completed scope",
  open_blockers: "Open blockers",
  open_high_severity_bugs: "Open high-severity bugs",
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
  if (metricName !== "open_blockers" && metricName !== "open_high_severity_bugs") {
    return null;
  }

  const issueKeys = metrics.metric_issue_keys[metricName];
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

function renderDeliveryConfidence(
  confidence: DeliveryConfidenceDetail,
  confidenceTrend: ConfidenceTrend | null,
  onSelectIssue: (issueKey: string) => void
) {
  const confidenceTrendTooltip = confidenceTrend ? getConfidenceTrendTooltip(confidenceTrend) : null;

  return (
    <div className="confidence-summary">
      <div className="confidence-score">
        <span className="confidence-label">
          <span className="muted">Delivery confidence</span>
          <button
            type="button"
            className="info-button"
            title="Delivery confidence is a weighted sprint health score. It combines progress alignment, velocity fit, blocker penalty, and scope stability to produce a single confidence value."
            aria-label="Delivery confidence info"
          >
            i
          </button>
          <a className="inline-anchor-link" href="#delivery-confidence-history">
            View graph comparison to recent 5 sprints
          </a>
        </span>
        <div className="confidence-score-value">
          <strong className={getDeliveryConfidenceClass(confidence.score)}>{confidence.score.toFixed(2)}</strong>
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
      </div>
      <div className="confidence-breakdown">
        {(Object.keys(confidence.components) as Array<keyof DeliveryConfidenceDetail["components"]>).map((key) => {
          const value = confidence.components[key];
          return (
            <div className="confidence-component" key={key}>
              <span className="confidence-component-label">
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
              </span>
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
            </div>
          );
        })}
      </div>
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
  const [isTicketSituationExpanded, setIsTicketSituationExpanded] = useState(false);
  const [sprintStoryPointRows, setSprintStoryPointRows] = useState<SprintStoryPointRow[]>([]);
  const [isLoadingSprintStoryPoints, setIsLoadingSprintStoryPoints] = useState(false);
  const [sprintStoryPointError, setSprintStoryPointError] = useState<string | null>(null);
  const [sprintConfidenceRows, setSprintConfidenceRows] = useState<SprintConfidenceRow[]>([]);
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
          apiClient.getSprintIssues(sprintId, 0, 100),
        ]);
        if (!isActive) {
          return;
        }
        setMetrics(metricsResponse);
        setIssues(issueResponse.items);
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
            return {
              sprint_id: sprint.sprint_id,
              name: sprint.name,
              delivery_confidence: Number(response.delivery_confidence.score.toFixed(2)),
              is_not_closed: isNotClosedSprint(sprint),
            };
          })
        );

        if (isActive) {
          setSprintConfidenceRows(results.filter((row): row is SprintConfidenceRow => row !== null));
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
        apiClient.getSprintIssues(selectedSprintId, 0, 100),
      ]);
      setMetrics(metricsResponse);
      setIssues(issueResponse.items);
      const recomputedConfidence = metricsResponse.delivery_confidence;
      if (recomputedConfidence) {
        setSprintConfidenceRows((currentRows) =>
          currentRows.map((row) =>
            row.sprint_id === selectedSprintId
              ? { ...row, delivery_confidence: Number(recomputedConfidence.score.toFixed(2)) }
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
      <section className="panel sprint-controls-panel">
        <div className="panel-heading">
          <h2>Sprint Metrics</h2>
        </div>
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
      </section>

      {errorMessage ? <div className="panel error-panel">{errorMessage}</div> : null}

      <section className="panel metrics-panel">
        {isLoadingDetails ? <p className="muted">Loading sprint metrics...</p> : null}
        {!isLoadingDetails && metrics && !metrics.is_computed ? (
          <p className="muted">Sprint metrics have not been computed yet.</p>
        ) : null}
        {!isLoadingDetails && metrics?.is_computed ? (
          <>
            {metrics.delivery_confidence
              ? renderDeliveryConfidence(metrics.delivery_confidence, confidenceTrend, onSelectIssue)
              : null}
            <div className="metric-grid">
              {metrics.delivery_confidence ? (
                <article className="metric-card" key="scope_changes">
                  <h3>Scope change tickets</h3>
                  <p className="metric-description">Issues added or removed from the sprint after it started.</p>
                  <strong>{metrics.delivery_confidence.inputs.scope_change_count}</strong>
                  {renderScopeIssueKeys(
                    "Scope change tickets",
                    metrics.delivery_confidence.inputs.scope_change_issue_keys ?? [],
                    issuesByKey,
                    onSelectIssue
                  )}
                </article>
              ) : null}
              {(Object.keys(metrics.metrics) as Array<keyof SprintMetricValues>)
                .filter((metricName) => metricName !== "delivery_confidence_score")
                .map((metricName) => (
                  <article className="metric-card" key={metricName}>
                    <h3>{sprintMetricLabels[metricName]}</h3>
                    <p className="metric-description">{sprintMetricDescriptions[metricName]}</p>
                    <strong>{formatMetricValue(metricName, metrics.metrics[metricName])}</strong>
                    {renderMetricIssueKeys(metricName, metrics.metrics[metricName], metrics, issuesByKey, onSelectIssue)}
                  </article>
                ))}
            </div>
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
        <div id="delivery-confidence-history" className="chart-section-heading first">
          <h3>Delivery confidence in recent sprints</h3>
          {sprintConfidenceRows.length > 0 ? <span className="muted">Last {sprintConfidenceRows.length}</span> : null}
        </div>
        {isLoadingSprintConfidence ? <p className="muted">Loading delivery confidence...</p> : null}
        {sprintConfidenceError ? <p className="error-text">{sprintConfidenceError}</p> : null}
        {!isLoadingSprintConfidence && !sprintConfidenceError && sprintConfidenceRows.length === 0 ? (
          <p className="muted">No sprint confidence data available yet.</p>
        ) : null}
        {!isLoadingSprintConfidence && !sprintConfidenceError && sprintConfidenceRows.length > 0 ? (
          <div className="chart-wrapper">
            <ResponsiveContainer width="100%" height={320}>
              <LineChart data={sprintConfidenceRows}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="name" />
                <YAxis domain={[0, 100]} />
                <Tooltip />
                <Legend />
                <Line
                  type="monotone"
                  dataKey="delivery_confidence"
                  name="Delivery confidence"
                  stroke={sprintConfidenceColor}
                  strokeWidth={2}
                  dot={{ r: 4 }}
                  activeDot={{ r: 6 }}
                />
              </LineChart>
            </ResponsiveContainer>
          </div>
        ) : null}

        <div className="chart-section-heading">
          <h3>Story points in every sprint</h3>
          {sprintStoryPointRows.length > 0 ? <span className="muted">Last {sprintStoryPointRows.length}</span> : null}
        </div>
        <div className="chart-legend-note" aria-label="Sprint state color legend">
          <span className="chart-legend-swatch not-closed" aria-hidden="true" />
          <span>All sprints in this color are not closed yet.</span>
        </div>
        {isLoadingSprintStoryPoints ? <p className="muted">Loading story points...</p> : null}
        {sprintStoryPointError ? <p className="error-text">{sprintStoryPointError}</p> : null}
        {!isLoadingSprintStoryPoints && !sprintStoryPointError && sprintStoryPointRows.length === 0 ? (
          <p className="muted">No sprint story point data available yet.</p>
        ) : null}
        {!isLoadingSprintStoryPoints && !sprintStoryPointError && sprintStoryPointRows.length > 0 ? (
          <div className="chart-wrapper">
            <ResponsiveContainer width="100%" height={320}>
              <BarChart data={sprintStoryPointRows}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="name" />
                <YAxis />
                <Tooltip />
                <Legend />
                <Bar
                  dataKey="story_points"
                  name="Story points"
                  fill={closedSprintStoryPointColor}
                  radius={[6, 6, 0, 0]}
                >
                  {sprintStoryPointRows.map((row) => (
                    <Cell
                      key={row.sprint_id}
                      fill={row.is_not_closed ? notClosedSprintStoryPointColor : closedSprintStoryPointColor}
                    />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        ) : null}
      </section>
    </div>
  );
}
