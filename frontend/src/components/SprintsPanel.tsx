import { useEffect, useMemo, useState } from "react";

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

function renderDeliveryConfidence(confidence: DeliveryConfidenceDetail, onSelectIssue: (issueKey: string) => void) {
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
        </span>
        <strong className={getDeliveryConfidenceClass(confidence.score)}>{confidence.score.toFixed(2)}</strong>
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
            {metrics.delivery_confidence ? renderDeliveryConfidence(metrics.delivery_confidence, onSelectIssue) : null}
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
    </div>
  );
}
