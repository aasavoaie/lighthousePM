import { useEffect, useMemo, useState } from "react";

import { apiClient } from "../api/client";
import type { Issue, MetricValues, ReleaseChartsResponse, ReleaseMetricsResponse } from "../api/types";
import { MetricSparkline, MetricColors } from "./ChartComponents";

interface MetricsPanelProps {
  metrics: ReleaseMetricsResponse | null;
  charts: ReleaseChartsResponse | null;
  isLoading: boolean;
  onSelectIssue: (issueKey: string) => void;
}

const metricLabels: Record<keyof MetricValues, string> = {
  open_blockers: "Open blockers",
  open_high_severity_bugs: "Open high-severity bugs",
  scope_completed_pct: "Scope completed",
  scope_churn_7d_pct: "Scope churn 7d",
  median_cycle_time_days: "Median cycle time (days)",
  reopen_rate_pct: "Reopen rate",
};

const metricDescriptions: Record<keyof MetricValues, string> = {
  open_blockers: "Release issues excluded from done status and classified as blockers by issue type (Blocker/Incident), priority (Blocker/Highest/Critical), status (Blocked), or the configured blocker field.",
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
  if (metricName === "scope_completed_pct" || metricName === "scope_churn_7d_pct" || metricName === "reopen_rate_pct") {
    return `${value.toFixed(2)}%`;
  }
  return value.toFixed(2);
}

const sparklineColorMap: Record<keyof MetricValues, string> = {
  open_blockers: MetricColors.blockers,
  open_high_severity_bugs: MetricColors.bugs,
  scope_completed_pct: MetricColors.scopeCompleted,
  scope_churn_7d_pct: MetricColors.scopeChurn,
  median_cycle_time_days: MetricColors.cycleTime,
  reopen_rate_pct: MetricColors.reopenRate,
};

function buildSparklineData(charts: ReleaseChartsResponse | null, metricName: keyof MetricValues) {
  if (!charts) {
    return [];
  }

  const series = charts.series[metricName as keyof typeof charts.series] ?? [];
  return series
    .filter((point) => point.value !== null)
    .map((point) => ({
      snapshot_at: new Date(point.snapshot_at).toLocaleDateString(),
      value: point.value as number,
    }));
}

function getIssueStatusClass(issueKey: string, issuesByKey: Record<string, Issue>) {
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

function renderMetricIssueKeys(
  metricName: keyof MetricValues,
  value: number | null,
  metrics: ReleaseMetricsResponse,
  issuesByKey: Record<string, Issue>,
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

export function MetricsPanel({ metrics, charts, isLoading, onSelectIssue }: MetricsPanelProps) {
  const metricIssueKeys = useMemo(() => {
    if (!metrics) {
      return [];
    }
    return Array.from(
      new Set([...metrics.metric_issue_keys.open_blockers, ...metrics.metric_issue_keys.open_high_severity_bugs])
    );
  }, [metrics]);
  const [metricIssuesByKey, setMetricIssuesByKey] = useState<Record<string, Issue>>({});

  useEffect(() => {
    if (metricIssueKeys.length === 0) {
      setMetricIssuesByKey({});
      return;
    }

    let isActive = true;

    async function loadMetricIssues() {
      const issueResults = await Promise.allSettled(metricIssueKeys.map((issueKey) => apiClient.getIssue(issueKey)));
      if (!isActive) {
        return;
      }
      const issuesByKey: Record<string, Issue> = {};
      for (const result of issueResults) {
        if (result.status === "fulfilled") {
          issuesByKey[result.value.issue_key] = result.value;
        }
      }
      setMetricIssuesByKey(issuesByKey);
    }

    void loadMetricIssues();

    return () => {
      isActive = false;
    };
  }, [metricIssueKeys]);

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
          {(Object.keys(metrics.metrics) as Array<keyof MetricValues>).map((metricName) => {
            const sparklineData = buildSparklineData(charts, metricName);
            return (
              <article className="metric-card" key={metricName}>
                <h3>{metricLabels[metricName]}</h3>
                <p className="metric-description">{metricDescriptions[metricName]}</p>
                <strong>{formatMetricValue(metricName, metrics.metrics[metricName])}</strong>
                <MetricSparkline
                  data={sparklineData}
                  valueKey="value"
                  lineColor={sparklineColorMap[metricName]}
                  empty={sparklineData.length === 0}
                  emptyMessage="Trend data unavailable"
                  formatter={(value, name) => formatMetricValue(metricName, value)}
                />
                {renderMetricIssueKeys(
                  metricName,
                  metrics.metrics[metricName],
                  metrics,
                  metricIssuesByKey,
                  onSelectIssue
                )}
              </article>
            );
          })}
        </div>
      ) : null}
    </section>
  );
}
