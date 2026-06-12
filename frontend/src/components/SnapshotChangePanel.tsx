import { useState } from "react";

import type {
  SnapshotBaseline,
  SnapshotChangeHistoryResponse,
  SnapshotComparisonResponse,
  SnapshotDeltaContributor,
} from "../api/types";

type SnapshotContext = "release" | "sprint";

interface SnapshotChangePanelProps {
  context: SnapshotContext;
  comparison: SnapshotComparisonResponse | null;
  history: SnapshotChangeHistoryResponse | null;
  baseline: SnapshotBaseline;
  isLoading: boolean;
  error: string | null;
  onBaselineChange: (baseline: SnapshotBaseline) => void;
}

const baselineLabels: Record<SnapshotBaseline, string> = {
  previous: "Previous snapshot",
  "24h": "Last 24h",
  "7d": "Last 7d",
};

const metricLabels: Record<string, string> = {
  open_blockers: "blockers",
  open_high_severity_bugs: "high-severity bugs",
  reopen_rate_pct: "reopen rate",
  median_cycle_time_days: "cycle time",
  scope_churn_7d_pct: "scope creep",
  completed_tickets: "completed work",
  velocity_fit: "velocity fit",
  scope_stability: "scope stability",
  progress_alignment: "progress alignment",
  blocker_health: "blocker health",
  bugs_created_during_sprint: "sprint-created bugs",
};

const countMetrics = new Set([
  "open_blockers",
  "open_high_severity_bugs",
  "completed_tickets",
  "bugs_created_during_sprint",
]);

function formatSigned(value: number) {
  if (value === 0) {
    return "0";
  }
  return `${value > 0 ? "+" : ""}${Number(value.toFixed(2))}`;
}

function formatConfidenceDelta(value: number) {
  if (value === 0) {
    return "Confidence unchanged";
  }
  return `Confidence ${formatSigned(value)}%`;
}

function formatDeltaValue(contributor: SnapshotDeltaContributor) {
  const absolute = Math.abs(contributor.delta);
  if (countMetrics.has(contributor.metric)) {
    return String(Number(absolute.toFixed(0)));
  }
  if (contributor.metric.endsWith("_pct")) {
    return `${Number(absolute.toFixed(2))}%`;
  }
  return Number(absolute.toFixed(2)).toString();
}

function formatContributorText(contributor: SnapshotDeltaContributor) {
  const label = metricLabels[contributor.metric] ?? contributor.metric;
  const value = formatDeltaValue(contributor);
  const improved = contributor.impact > 0;

  if (contributor.metric === "open_blockers") {
    return `${value} blockers ${contributor.direction === "down" ? "resolved" : "opened"}`;
  }
  if (contributor.metric === "open_high_severity_bugs") {
    return `${value} high-severity bugs ${contributor.direction === "down" ? "fixed" : "opened"}`;
  }
  if (contributor.metric === "bugs_created_during_sprint") {
    return `${value} sprint-created bugs ${contributor.direction === "down" ? "cleared" : "added"}`;
  }
  if (contributor.metric === "completed_tickets") {
    return `${value} tickets ${contributor.direction === "up" ? "completed" : "removed from completed work"}`;
  }
  return `${label} ${improved ? "improved" : contributor.impact < 0 ? "worsened" : "changed"}`;
}

function metricLabel(metric: string) {
  return metricLabels[metric] ?? metric;
}

function renderContributor(contributor: SnapshotDeltaContributor) {
  const impactClass = contributor.impact > 0 ? "positive" : contributor.impact < 0 ? "negative" : "neutral";
  return (
    <li className={`snapshot-change-item ${impactClass}`} key={`${contributor.metric}-${contributor.delta}`}>
      <span className="snapshot-change-arrow" aria-hidden="true">
        {contributor.impact > 0 ? "↑" : contributor.impact < 0 ? "↓" : "-"}
      </span>
      <span>{formatContributorText(contributor)}</span>
      <strong>({formatSigned(contributor.impact)})</strong>
    </li>
  );
}

function renderHistory(history: SnapshotChangeHistoryResponse | null) {
  if (!history || history.items.length === 0) {
    return <p className="muted">No snapshot change history available yet.</p>;
  }

  return (
    <div className="table-wrapper snapshot-history-wrapper">
      <table className="issues-table snapshot-history-table">
        <thead>
          <tr>
            <th>Date</th>
            <th>Confidence</th>
            <th>Delta</th>
            <th>Primary driver</th>
          </tr>
        </thead>
        <tbody>
          {history.items.map((item) => (
            <tr key={item.date}>
              <td>{new Date(item.date).toLocaleString()}</td>
              <td>{item.confidence === null ? "N/A" : `${Math.round(item.confidence)}%`}</td>
              <td>{item.delta === null ? "N/A" : `${formatSigned(item.delta)}%`}</td>
              <td>{metricLabel(item.primary_driver)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function SnapshotChangePanel({
  context,
  comparison,
  history,
  baseline,
  isLoading,
  error,
  onBaselineChange,
}: SnapshotChangePanelProps) {
  const contributors = comparison?.comparison.contributors ?? [];
  const hasBaseline = comparison?.has_baseline ?? false;
  const [isHistoryExpanded, setIsHistoryExpanded] = useState(false);

  return (
    <section className="snapshot-change-panel">
      <div className="chart-section-heading first">
        <div>
          <h3>What's Changed</h3>
          <p className="chart-section-subtitle">
            {context === "release" ? "Explains release confidence movement from stored snapshots." : "Explains sprint confidence movement from stored snapshots."}
          </p>
        </div>
        <div className="baseline-segmented-control" role="group" aria-label="Snapshot comparison baseline">
          {(Object.keys(baselineLabels) as SnapshotBaseline[]).map((option) => (
            <button
              type="button"
              className={option === baseline ? "active" : ""}
              key={option}
              onClick={() => onBaselineChange(option)}
            >
              {baselineLabels[option]}
            </button>
          ))}
        </div>
      </div>
      {isLoading ? <p className="muted">Loading snapshot changes...</p> : null}
      {error ? <p className="error-text">{error}</p> : null}
      {!isLoading && !error ? (
        <div className="snapshot-change-summary">
          <strong>{formatConfidenceDelta(comparison?.comparison.confidenceDelta ?? 0)}</strong>
          {hasBaseline ? (
            contributors.length > 0 ? (
              <ul className="snapshot-change-list">{contributors.map(renderContributor)}</ul>
            ) : (
              <p className="muted">No measured contributor changed.</p>
            )
          ) : (
            <p className="muted">No baseline snapshot available for {baselineLabels[baseline].toLowerCase()}.</p>
          )}
        </div>
      ) : null}

      <div className="chart-section-heading snapshot-history-heading">
        <div>
          <h3>Snapshot Change History</h3>
          <p className="chart-section-subtitle">Confidence, delta, and primary driver by snapshot.</p>
        </div>
        <button
          type="button"
          className="secondary-button compact-button"
          aria-controls="snapshot-change-history"
          aria-expanded={isHistoryExpanded}
          onClick={() => setIsHistoryExpanded((current) => !current)}
        >
          {isHistoryExpanded ? "Minimize" : "Expand"}
        </button>
      </div>
      {isHistoryExpanded && !isLoading && !error ? (
        <div id="snapshot-change-history">{renderHistory(history)}</div>
      ) : null}
    </section>
  );
}
