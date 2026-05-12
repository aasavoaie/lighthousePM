import type { MetricValues, ReleaseMetricsResponse } from "../api/types";

interface MetricsPanelProps {
  metrics: ReleaseMetricsResponse | null;
  isLoading: boolean;
  onSelectIssue: (issueKey: string) => void;
}

const metricLabels: Record<keyof MetricValues, string> = {
  open_blockers: "Open blockers",
  open_high_severity_bugs: "Open high-severity bugs",
  scope_completed_pct: "Scope completed %",
  scope_churn_7d_pct: "Scope churn 7d %",
  median_cycle_time_days: "Median cycle time (days)",
  reopen_rate_pct: "Reopen rate %",
};

const metricDescriptions: Record<keyof MetricValues, string> = {
  open_blockers:
    "Open, non-done issues classified as blockers by Jira type/priority or explicit blocker flag.",
  open_high_severity_bugs: "Open bugs with high or critical severity levels.",
  scope_completed_pct: "Percentage of release issues currently in done status.",
  scope_churn_7d_pct: "Scope changes affecting this release during the last 7 days.",
  median_cycle_time_days: "Median days from first in-progress to first done transition.",
  reopen_rate_pct: "Share of release issues that moved from done back to active work.",
};

function formatMetricValue(metricName: keyof MetricValues, value: number | null) {
  if (value === null) {
    return "N/A";
  }
  if (metricName === "open_blockers" || metricName === "open_high_severity_bugs") {
    return String(value);
  }
  return value.toFixed(2);
}

function renderMetricIssueKeys(
  metricName: keyof MetricValues,
  value: number | null,
  metrics: ReleaseMetricsResponse,
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
    <ul className="metric-ticket-list" aria-label={`${metricLabels[metricName]} tickets`}>
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

export function MetricsPanel({ metrics, isLoading, onSelectIssue }: MetricsPanelProps) {
  return (
    <section className="panel metrics-panel">
      <div className="panel-heading">
        <h2>Metrics</h2>
        {metrics?.snapshot_age_hours !== null && metrics?.snapshot_age_hours !== undefined ? (
          <span className="muted">Age {metrics.snapshot_age_hours.toFixed(1)}h</span>
        ) : null}
      </div>
      {isLoading ? <p className="muted">Loading metrics...</p> : null}
      {!isLoading && metrics && !metrics.is_computed ? (
        <p className="muted">Metrics have not been computed for this release yet.</p>
      ) : null}
      {!isLoading && metrics && metrics.is_computed ? (
        <div className="metric-grid">
          {(Object.keys(metrics.metrics) as Array<keyof MetricValues>).map((metricName) => (
            <article className="metric-card" key={metricName}>
              <h3>{metricLabels[metricName]}</h3>
              <p className="metric-description">{metricDescriptions[metricName]}</p>
              <strong>{formatMetricValue(metricName, metrics.metrics[metricName])}</strong>
              {renderMetricIssueKeys(metricName, metrics.metrics[metricName], metrics, onSelectIssue)}
            </article>
          ))}
        </div>
      ) : null}
    </section>
  );
}
