import { useEffect, useMemo, useState } from "react";

import { apiClient } from "../api/client";
import type { Issue, Sprint, SprintMetricValues, SprintMetricsResponse } from "../api/types";

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
  rollover_count: "Rollover",
  median_cycle_time_days: "Median cycle time",
  reopen_rate_pct: "Reopen rate %",
};

const sprintMetricDescriptions: Record<keyof SprintMetricValues, string> = {
  committed_scope: "Issues explicitly linked to this sprint.",
  completed_scope_pct: "Done issues divided by total sprint issues.",
  open_blockers: "Open sprint issues currently flagged as blockers.",
  open_high_severity_bugs: "Open sprint bugs with high or critical priority.",
  in_progress_count: "Sprint issues in configured in-progress statuses.",
  not_started_count: "Sprint issues that are neither in progress nor done.",
  rollover_count: "Closed-sprint issues that did not reach done.",
  median_cycle_time_days: "Median days from first in-progress to first done.",
  reopen_rate_pct: "Sprint issues that moved from done back to active work.",
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
  return value.toFixed(2);
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
  const [issues, setIssues] = useState<Issue[]>([]);
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
      </section>

      {errorMessage ? <div className="panel error-panel">{errorMessage}</div> : null}

      <section className="panel metrics-panel">
        {isLoadingDetails ? <p className="muted">Loading sprint metrics...</p> : null}
        {!isLoadingDetails && metrics && !metrics.is_computed ? (
          <p className="muted">Sprint metrics have not been computed yet.</p>
        ) : null}
        {!isLoadingDetails && metrics?.is_computed ? (
          <div className="metric-grid">
            {(Object.keys(metrics.metrics) as Array<keyof SprintMetricValues>).map((metricName) => (
              <article className="metric-card" key={metricName}>
                <h3>{sprintMetricLabels[metricName]}</h3>
                <p className="metric-description">{sprintMetricDescriptions[metricName]}</p>
                <strong>{formatMetricValue(metricName, metrics.metrics[metricName])}</strong>
                {renderMetricIssueKeys(metricName, metrics.metrics[metricName], metrics, onSelectIssue)}
              </article>
            ))}
          </div>
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
