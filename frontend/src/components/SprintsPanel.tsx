import { useEffect, useMemo, useState } from "react";

import { apiClient } from "../api/client";
import type {
  DeliveryConfidenceDetail,
  RecomputeSprintMetricsResponse,
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
  completed_scope_pct: "Completed scope %",
  open_blockers: "Open blockers",
  open_high_severity_bugs: "Open high-severity bugs",
  in_progress_count: "In progress",
  not_started_count: "Not started",
  blocked_count: "Tickets in Blocked Column",
  rollover_count: "Rollover",
  median_cycle_time_days: "Median cycle time",
  reopen_rate_pct: "Reopen rate %",
  delivery_confidence_score: "Delivery confidence",
};

const sprintMetricDescriptions: Record<keyof SprintMetricValues, string> = {
  committed_scope: "Issues explicitly linked to this sprint.",
  completed_scope_pct: "Done issues divided by total sprint issues.",
  open_blockers:
    "Open sprint issues classified as blockers by Jira type/priority or explicit blocker flag, excluding done statuses.",
  open_high_severity_bugs: "Open sprint bugs with high or critical priority.",
  in_progress_count: "Sprint issues in configured in-progress statuses.",
  not_started_count: "Sprint issues that are neither in progress nor done.",
  blocked_count: "Sprint issues currently in configured blocked statuses.",
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

const deliveryConfidenceExplanations: Record<string, string> = {
  "Points in sprint": "Sum of story points (or 1 point if no estimate) for all issues currently assigned to the sprint. Represents the total committed work.",
  "Completed pts": "Sum of story points for issues that have reached done status. Measures actual completed work.",
  "Remaining pts": "Committed pts minus Completed pts. Shows remaining work to be done.",
  "Elapsed": "Percentage of sprint time that has passed, calculated as (current time - sprint start) / (sprint end - sprint start) × 100. Null if sprint hasn't started or dates are missing.",
  "Velocity": "Points completed per day in the current sprint, calculated as Completed pts ÷ days since sprint start. Null if sprint hasn't started.",
  "Baseline": "Number of historical sprints used to calculate the baseline velocity for comparison. Uses the most recent completed sprints (up to 3).",
  "Blocked ratio": "Ratio of currently blocked issues to total sprint issues. Calculated as blocked_count ÷ total_issue_count.",
  "Scope changes": "Total number of issues added to or removed from the sprint after it started. Calculated as scope_added_count + scope_removed_count.",
};

function InfoIcon({ explanation }: { explanation: string }) {
  return (
    <span
      className="info-icon"
      title={explanation}
      aria-label="Information"
      role="tooltip"
    >
      ℹ️
    </span>
  );
}

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
    metricName === "blocked_count" ||
    metricName === "rollover_count"
  ) {
    return String(value);
  }
  return value.toFixed(2);
}

function formatNullableNumber(value: number | null | undefined, suffix = "") {
  if (value === null || value === undefined) {
    return "N/A";
  }
  return `${value.toFixed(2)}${suffix}`;
}

function renderScopeIssueKeys(label: string, issueKeys: string[], onSelectIssue: (issueKey: string) => void) {
  if (issueKeys.length === 0) {
    return null;
  }
  return (
    <div className="scope-ticket-group">
      <span className="muted">{label}</span>
      <ul className="metric-ticket-list" aria-label={`${label} tickets`}>
        {issueKeys.map((issueKey) => (
          <li key={issueKey}>
            <button type="button" className="link-button" onClick={() => onSelectIssue(issueKey)}>
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
          <button type="button" className="link-button" onClick={() => onSelectIssue(issueKey)}>
            {issueKey}
          </button>
        </li>
      ))}
    </ul>
  );
}

function renderDeliveryConfidence(confidence: DeliveryConfidenceDetail, onSelectIssue: (issueKey: string) => void) {
  const isScopeStabilityExcluded = confidence.components.scope_stability === null;

  return (
    <div className="confidence-summary">
      <div className="confidence-score">
        <span className="muted">
          Delivery confidence
          {isScopeStabilityExcluded ? <span className="confidence-note">Excluded: no initial commitment</span> : null}
        </span>
        <strong>{confidence.score.toFixed(2)}</strong>
      </div>
      <div className="confidence-breakdown">
        {(Object.keys(confidence.components) as Array<keyof DeliveryConfidenceDetail["components"]>).map((key) => (
          <div className="confidence-component" key={key}>
            <span>{confidenceComponentLabels[key]}</span>
            <strong>{formatNullableNumber(confidence.components[key])}</strong>
          </div>
        ))}
      </div>
      <dl className="confidence-inputs">
        <dt>Points in sprint <InfoIcon explanation={deliveryConfidenceExplanations["Points in sprint"]} /></dt>
        <dd>{Math.round(confidence.inputs.committed_effective_points)}</dd>
        <dt>Completed pts <InfoIcon explanation={deliveryConfidenceExplanations["Completed pts"]} /></dt>
        <dd>{Math.round(confidence.inputs.completed_effective_points)}</dd>
        <dt>Remaining pts <InfoIcon explanation={deliveryConfidenceExplanations["Remaining pts"]} /></dt>
        <dd>{Math.round(confidence.inputs.remaining_effective_points)}</dd>
        <dt>Elapsed <InfoIcon explanation={deliveryConfidenceExplanations["Elapsed"]} /></dt>
        <dd>{formatNullableNumber(confidence.inputs.time_elapsed_pct, "%")}</dd>
        <dt>Velocity <InfoIcon explanation={deliveryConfidenceExplanations["Velocity"]} /></dt>
        <dd>{formatNullableNumber(confidence.inputs.historical_velocity)}</dd>
        <dt>Baseline <InfoIcon explanation={deliveryConfidenceExplanations["Baseline"]} /></dt>
        <dd>{confidence.inputs.baseline_sprint_count}</dd>
        <dt>Blocked ratio <InfoIcon explanation={deliveryConfidenceExplanations["Blocked ratio"]} /></dt>
        <dd>{confidence.inputs.blocked_issue_ratio.toFixed(4)}</dd>
        <dt>Scope changes <InfoIcon explanation={deliveryConfidenceExplanations["Scope changes"]} /></dt>
        <dd>{confidence.inputs.scope_change_count}</dd>
      </dl>
    </div>
  );
}

function renderScopeStabilityIndex(confidence: DeliveryConfidenceDetail, onSelectIssue: (issueKey: string) => void) {
  const inputs = confidence.inputs;
  const initialCommitment = inputs.initial_commitment_count ?? inputs.committed_issue_count;
  const addedCount = inputs.scope_added_count ?? 0;
  const removedCount = inputs.scope_removed_count ?? 0;
  const scopeStabilityIndex = inputs.scope_stability_index ?? null;
  const addedIssueKeys = inputs.scope_added_issue_keys ?? [];
  const removedIssueKeys = inputs.scope_removed_issue_keys ?? [];
  const addedBeforeStartIssueKeys = inputs.scope_added_before_start_issue_keys ?? [];

  return (
    <div className="scope-stability-summary">
      <div className="scope-stability-headline">
        <div>
          <span className="muted">Scope Stability Index</span>
          <p className="metric-description">Added plus removed issues divided by initial commitment.</p>
        </div>
        <strong>{formatNullableNumber(scopeStabilityIndex)}</strong>
      </div>
      <dl className="scope-stability-inputs">
        <dt>Added</dt>
        <dd>{addedCount}</dd>
        <dt>Removed</dt>
        <dd>{removedCount}</dd>
        <dt>Initial commitment</dt>
        <dd>{initialCommitment}</dd>
        <dt>Formula</dt>
        <dd>
          ({addedCount} + {removedCount}) / {initialCommitment}
        </dd>
      </dl>
      <p className="scope-stability-insight">
        {scopeStabilityIndex === null
          ? "No ticket added before sprint start."
          : scopeStabilityIndex === 0
            ? "No post-start scope movement recorded."
            : "Higher volatility lowers delivery confidence."}
      </p>
      <div className="scope-ticket-lists">
        {renderScopeIssueKeys("Added before start", addedBeforeStartIssueKeys, onSelectIssue)}
        {renderScopeIssueKeys("Added after start", addedIssueKeys, onSelectIssue)}
        {renderScopeIssueKeys("Removed after start", removedIssueKeys, onSelectIssue)}
      </div>
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
  const [recomputeTrend, setRecomputeTrend] = useState<{
    trend: "ascending" | "declining" | "unchanged" | "unknown" | null;
    delta: number | null;
    previousScore: number | null;
  } | null>(null);
  const [isLoadingList, setIsLoadingList] = useState(true);
  const [isLoadingDetails, setIsLoadingDetails] = useState(false);
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
      setRecomputeTrend(null);
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
      const response = await apiClient.recomputeSprint(selectedSprintId);
      setRecomputeTrend({
        trend: response.delivery_confidence_trend,
        delta: response.delivery_confidence_delta,
        previousScore: response.previous_delivery_confidence_score,
      });
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
    <>
      <section className="panel selector-panel">
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
      </section>

      <section className="panel action-panel">
        <div className="panel-heading">
          <h2>Sprint Metrics</h2>
        </div>
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
        {recomputeTrend ? (
          <p className={`muted recompute-trend recompute-trend-${recomputeTrend.trend}`}>
            {recomputeTrend.trend === "ascending" && recomputeTrend.delta !== null
              ? `Delivery confidence is ascending by ${recomputeTrend.delta.toFixed(2)} points.`
              : recomputeTrend.trend === "declining" && recomputeTrend.delta !== null
              ? `Delivery confidence is declining by ${Math.abs(recomputeTrend.delta).toFixed(2)} points.`
              : recomputeTrend.trend === "unchanged"
              ? "Delivery confidence is unchanged from the previous snapshot."
              : "No previous delivery confidence snapshot available for comparison."}
          </p>
        ) : null}
      </section>

      {errorMessage ? <div className="panel error-panel">{errorMessage}</div> : null}

      <section className="panel metrics-panel">
        {isLoadingDetails ? <p className="muted">Loading sprint metrics...</p> : null}
        {!isLoadingDetails && metrics && !metrics.is_computed ? (
          <p className="muted">Sprint metrics have not been computed yet.</p>
        ) : null}
        {!isLoadingDetails && metrics?.is_computed ? (
          <>
            {metrics.delivery_confidence ? renderScopeStabilityIndex(metrics.delivery_confidence, onSelectIssue) : null}
            {metrics.delivery_confidence ? renderDeliveryConfidence(metrics.delivery_confidence, onSelectIssue) : null}
            <div className="metric-grid">
              {(Object.keys(metrics.metrics) as Array<keyof SprintMetricValues>)
                .filter((metricName) => metricName !== "delivery_confidence_score")
                .map((metricName) => (
                  <article className="metric-card" key={metricName}>
                    <h3>{sprintMetricLabels[metricName]}</h3>
                    <p className="metric-description">{sprintMetricDescriptions[metricName]}</p>
                    <strong>{formatMetricValue(metricName, metrics.metrics[metricName])}</strong>
                    {renderMetricIssueKeys(metricName, metrics.metrics[metricName], metrics, onSelectIssue)}
                  </article>
                ))}
            </div>
          </>
        ) : null}
      </section>

      <section className="panel issues-panel">
        <div className="panel-heading">
          <h2>Sprint Issues</h2>
          <span className="muted">{issues.length} shown</span>
        </div>
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
      </section>
    </>
  );
}
