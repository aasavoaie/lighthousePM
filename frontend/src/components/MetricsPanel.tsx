import { useEffect, useMemo, useState } from "react";

import { apiClient } from "../api/client";
import type { Issue, MetricValues, ReleaseChartsResponse, ReleaseMetricsResponse } from "../api/types";
import { MetricSparkline, MetricColors } from "./ChartComponents";
import {
  MetricCategorySection,
  MetricStatusCard,
  type MetricImpact,
  type MetricStatus,
  formatSignedDelta,
  getDeltaImpact,
} from "./MetricCards";

interface MetricsPanelProps {
  metrics: ReleaseMetricsResponse | null;
  charts: ReleaseChartsResponse | null;
  isLoading: boolean;
  onSelectIssue: (issueKey: string) => void;
  focusedMetricName?: keyof MetricValues | null;
}

const metricLabels: Record<keyof MetricValues, string> = {
  open_blockers: "Open blockers",
  open_high_severity_bugs: "Open high-severity bugs",
  scope_completed_pct: "Scope completed",
  completed_tickets: "Completed tickets",
  scope_churn_7d_pct: "Scope creep",
  scope_added_7d_count: "Scope added",
  scope_removed_7d_count: "Scope removed",
  median_cycle_time_days: "Median cycle time (days)",
  reopen_rate_pct: "Reopen rate",
};

const metricDirections: Record<keyof MetricValues, "higher-is-better" | "lower-is-better" | "neutral"> = {
  open_blockers: "lower-is-better",
  open_high_severity_bugs: "lower-is-better",
  scope_completed_pct: "higher-is-better",
  completed_tickets: "neutral",
  scope_churn_7d_pct: "lower-is-better",
  scope_added_7d_count: "lower-is-better",
  scope_removed_7d_count: "lower-is-better",
  median_cycle_time_days: "lower-is-better",
  reopen_rate_pct: "lower-is-better",
};

function formatMetricValue(metricName: keyof MetricValues, value: number | null) {
  if (value === null) {
    return "N/A";
  }
  if (
    metricName === "open_blockers" ||
    metricName === "open_high_severity_bugs" ||
    metricName === "scope_added_7d_count" ||
    metricName === "scope_removed_7d_count"
  ) {
    return String(value);
  }
  if (metricName === "completed_tickets") {
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
  completed_tickets: MetricColors.completedTickets,
  scope_churn_7d_pct: MetricColors.scopeChurn,
  scope_added_7d_count: MetricColors.scopeChurn,
  scope_removed_7d_count: MetricColors.scopeChurn,
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

function getLatestDelta(charts: ReleaseChartsResponse | null, metricName: keyof MetricValues) {
  const points = charts?.series[metricName] ?? [];
  const numericPoints = points.filter((point) => point.value !== null);
  if (numericPoints.length < 2) {
    return null;
  }
  const previous = numericPoints[numericPoints.length - 2].value as number;
  const current = numericPoints[numericPoints.length - 1].value as number;
  return Number((current - previous).toFixed(2));
}

function buildComparison(charts: ReleaseChartsResponse | null, metricName: keyof MetricValues) {
  const delta = getLatestDelta(charts, metricName);
  if (delta === null) {
    return { text: "Trend baseline unavailable", impact: "unknown" as MetricImpact };
  }
  return {
    text: formatSignedDelta(delta, (value) => formatMetricValue(metricName, value)),
    impact: getDeltaImpact(delta, metricDirections[metricName]),
  };
}

function getReleaseMetricStatus(
  metricName: keyof MetricValues,
  value: number | null,
  metrics: ReleaseMetricsResponse
): MetricStatus {
  if (value === null) {
    return "neutral";
  }

  const thresholds = metrics.metric_thresholds;
  if (metricName === "open_blockers") {
    return thresholds && value > thresholds.open_blockers_red ? "critical" : "good";
  }
  if (metricName === "open_high_severity_bugs") {
    if (!thresholds) {
      return "neutral";
    }
    if (value > thresholds.open_high_severity_bugs_red) {
      return "critical";
    }
    return value > thresholds.open_high_severity_bugs_yellow ? "warning" : "good";
  }
  if (metricName === "scope_churn_7d_pct") {
    if (!thresholds) {
      return "neutral";
    }
    if (value > thresholds.scope_churn_7d_pct_red) {
      return "critical";
    }
    return value > thresholds.scope_churn_7d_pct_yellow ? "warning" : "good";
  }
  if (metricName === "reopen_rate_pct") {
    if (!thresholds) {
      return "neutral";
    }
    if (value > thresholds.reopen_rate_pct_red) {
      return "critical";
    }
    return value > thresholds.reopen_rate_pct_yellow ? "warning" : "good";
  }
  if (metricName === "median_cycle_time_days") {
    return thresholds && value > thresholds.median_cycle_time_days_yellow ? "warning" : "good";
  }
  if (metricName === "scope_completed_pct") {
    if (value >= 80) {
      return "good";
    }
    return value >= 50 ? "warning" : "critical";
  }
  return "neutral";
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

export function MetricsPanel({ metrics, charts, isLoading, onSelectIssue, focusedMetricName = null }: MetricsPanelProps) {
  const metricIssueKeys = useMemo(() => {
    if (!metrics) {
      return [];
    }
    return Array.from(
      new Set([...metrics.metric_issue_keys.open_blockers, ...metrics.metric_issue_keys.open_high_severity_bugs])
    );
  }, [metrics]);
  const [metricIssuesByKey, setMetricIssuesByKey] = useState<Record<string, Issue>>({});
  const [isMetricsExpanded, setIsMetricsExpanded] = useState(true);

  function renderReleaseMetricCard(metricName: keyof MetricValues, options?: { details?: string[] }) {
    if (!metrics) {
      return null;
    }

    const value = metrics.metrics[metricName];
    const sparklineData = buildSparklineData(charts, metricName);
    const comparison = buildComparison(charts, metricName);
    return (
      <MetricStatusCard
        id={`release-metric-${metricName}`}
        key={metricName}
        title={metricLabels[metricName]}
        value={formatMetricValue(metricName, value)}
        status={getReleaseMetricStatus(metricName, value, metrics)}
        isHighlighted={focusedMetricName === metricName}
        comparison={comparison.text}
        comparisonImpact={comparison.impact}
        details={options?.details}
      >
        <MetricSparkline
          data={sparklineData}
          valueKey="value"
          lineColor={sparklineColorMap[metricName]}
          empty={sparklineData.length === 0}
          emptyMessage="Trend data unavailable"
          formatter={(pointValue) => formatMetricValue(metricName, pointValue)}
        />
        {renderMetricIssueKeys(metricName, value, metrics, metricIssuesByKey, onSelectIssue)}
      </MetricStatusCard>
    );
  }

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
        <div className="panel-heading-actions">
          {metrics?.snapshot_age_hours !== null && metrics?.snapshot_age_hours !== undefined ? (
            <span className="muted">Age {metrics.snapshot_age_hours.toFixed(1)}h</span>
          ) : null}
          <button
            type="button"
            className="secondary-button compact-button"
            aria-expanded={isMetricsExpanded}
            onClick={() => setIsMetricsExpanded((current) => !current)}
          >
            {isMetricsExpanded ? "Minimize" : "Expand"}
          </button>
        </div>
      </div>
      {isMetricsExpanded ? (
        <>
          {isLoading ? <p className="muted">Loading metrics...</p> : null}
          {!isLoading && metrics && !metrics.is_computed ? (
            <p className="muted">Metrics have not been computed for this release yet.</p>
          ) : null}
          {!isLoading && metrics && metrics.is_computed ? (
            <div className="metric-category-stack">
              <MetricCategorySection title="Delivery">
                {renderReleaseMetricCard("scope_completed_pct")}
                {renderReleaseMetricCard("completed_tickets")}
                {renderReleaseMetricCard("scope_churn_7d_pct", {
                  details: [
                    `${metrics.metrics.scope_added_7d_count ?? 0} issues added`,
                    `${metrics.metrics.scope_removed_7d_count ?? 0} issues removed`,
                  ],
                })}
              </MetricCategorySection>
              <MetricCategorySection title="Quality">
                {renderReleaseMetricCard("open_high_severity_bugs")}
                {renderReleaseMetricCard("reopen_rate_pct")}
              </MetricCategorySection>
              <MetricCategorySection title="Flow">{renderReleaseMetricCard("median_cycle_time_days")}</MetricCategorySection>
              <MetricCategorySection title="Risk">{renderReleaseMetricCard("open_blockers")}</MetricCategorySection>
            </div>
          ) : null}
        </>
      ) : null}
    </section>
  );
}
