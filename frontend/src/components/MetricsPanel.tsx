import type { MetricValues, ReleaseMetricsResponse } from "../api/types";

interface MetricsPanelProps {
  metrics: ReleaseMetricsResponse | null;
  isLoading: boolean;
}

const metricLabels: Record<keyof MetricValues, string> = {
  open_blockers: "Open blockers",
  open_high_severity_bugs: "Open high-severity bugs",
  scope_completed_pct: "Scope completed %",
  scope_churn_7d_pct: "Scope churn 7d %",
  median_cycle_time_days: "Median cycle time (days)",
  reopen_rate_pct: "Reopen rate %",
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

export function MetricsPanel({ metrics, isLoading }: MetricsPanelProps) {
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
              <strong>{formatMetricValue(metricName, metrics.metrics[metricName])}</strong>
            </article>
          ))}
        </div>
      ) : null}
    </section>
  );
}