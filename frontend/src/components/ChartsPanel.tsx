import { useEffect, useMemo, useState } from "react";

import { apiClient } from "../api/client";
import type {
  MetricSeries,
  Release,
  ReleaseChartsResponse,
  ReleaseMetricsResponse,
  ReleaseSignalResponse,
  SignalRiskAgingGroup,
  SnapshotBaseline,
  SnapshotChangeHistoryResponse,
  SnapshotComparisonResponse,
} from "../api/types";
import {
  MetricBarChart,
  MetricColors,
  MetricHorizontalBarChart,
  MetricLineChart,
  formatPercentage,
} from "./ChartComponents";
import { BiggestDriverCard } from "./BiggestDriverCard";
import { RecommendationsPanel } from "./RecommendationsPanel";
import { SnapshotChangePanel } from "./SnapshotChangePanel";

interface ChartsPanelProps {
  charts: ReleaseChartsResponse | null;
  signal: ReleaseSignalResponse | null;
  metrics: ReleaseMetricsResponse | null;
  releases: Release[];
  selectedProjectKey: string | null;
  selectedReleaseName: string | null;
  refreshNonce: number;
  isLoading: boolean;
}

type ChartMetricName = keyof MetricSeries;

type ReleaseComparisonRow = {
  release_id: string;
  name: string;
  confidence_score: number | null;
  blockers: number | null;
  bugs: number | null;
  reopen_rate_pct: number | null;
  is_unreleased: boolean;
};

type RiskContributionRow = {
  name: string;
  metric_name: string;
  level: string;
  contribution_pct: number;
};

type BlockerAgingRow = {
  name: string;
  count: number;
};

const chartMetricLabels: Record<ChartMetricName, string> = {
  open_blockers: "Open blockers",
  open_high_severity_bugs: "High-severity bugs",
  scope_completed_pct: "Scope completed",
  completed_tickets: "Completed tickets",
  scope_churn_7d_pct: "Scope churn",
  scope_added_7d_count: "Scope added",
  scope_removed_7d_count: "Scope removed",
  median_cycle_time_days: "Median cycle time",
  reopen_rate_pct: "Reopen rate",
  confidence_score: "Confidence",
  gates_passed_count: "Gates passed",
  readiness_pct: "Readiness",
};

const riskMetricColors: Record<string, string> = {
  open_blockers: MetricColors.blockers,
  open_high_severity_bugs: MetricColors.bugs,
  scope_churn_7d_pct: MetricColors.scopeChurn,
  median_cycle_time_days: MetricColors.cycleTime,
  reopen_rate_pct: MetricColors.reopenRate,
};

function buildSingleMetricRows(charts: ReleaseChartsResponse | null, metricName: ChartMetricName) {
  if (!charts) {
    return [];
  }

  return charts.series[metricName].map((point) => ({
    snapshot_at: new Date(point.snapshot_at).toLocaleDateString(),
    value: point.value,
  }));
}

function releaseSortTime(release: Release) {
  const primaryDate = release.release_date ?? release.created_at;
  const parsed = Date.parse(primaryDate);
  return Number.isFinite(parsed) ? parsed : 0;
}

function getRecentReleases(releases: Release[], projectKey: string | null) {
  const scopedReleases = projectKey ? releases.filter((release) => release.project_key === projectKey) : releases;
  return [...scopedReleases]
    .sort((left, right) => releaseSortTime(right) - releaseSortTime(left))
    .slice(0, 5)
    .reverse();
}

function isUnreleasedRelease(release: Release) {
  return (release.status ?? "").trim().toLowerCase() !== "released";
}

function riskLabel(metricName: string) {
  return chartMetricLabels[metricName as ChartMetricName] ?? metricName;
}

function buildRiskContributionRows(signal: ReleaseSignalResponse | null): RiskContributionRow[] {
  if (!signal) {
    return [];
  }

  const rowsByMetric = new Map<string, RiskContributionRow>();
  for (const item of [...signal.critical_risks, ...signal.warnings]) {
    const existing = rowsByMetric.get(item.metric_name);
    if (!existing || item.contribution_pct > existing.contribution_pct) {
      rowsByMetric.set(item.metric_name, {
        name: riskLabel(item.metric_name),
        metric_name: item.metric_name,
        level: item.level,
        contribution_pct: item.contribution_pct,
      });
    }
  }

  return Array.from(rowsByMetric.values())
    .filter((row) => row.contribution_pct > 0)
    .sort((left, right) => right.contribution_pct - left.contribution_pct || left.name.localeCompare(right.name));
}

function buildBlockerAgingRows(group: SignalRiskAgingGroup | null | undefined): BlockerAgingRow[] {
  const rows: BlockerAgingRow[] = [
    { name: "0-3 days", count: 0 },
    { name: "4-7 days", count: 0 },
    { name: "8-14 days", count: 0 },
    { name: "15+ days", count: 0 },
  ];

  for (const ticket of group?.tickets ?? []) {
    if (ticket.age_days <= 3) {
      rows[0].count += 1;
    } else if (ticket.age_days <= 7) {
      rows[1].count += 1;
    } else if (ticket.age_days <= 14) {
      rows[2].count += 1;
    } else {
      rows[3].count += 1;
    }
  }

  return rows;
}

function formatNullableNumber(value: number | null | undefined) {
  if (value === null || value === undefined) {
    return "N/A";
  }
  return Number.isInteger(value) ? value.toFixed(0) : value.toFixed(1);
}

function formatNullablePct(value: number | null | undefined) {
  if (value === null || value === undefined) {
    return "N/A";
  }
  return `${value.toFixed(0)}%`;
}

function renderComparisonTable(rows: ReleaseComparisonRow[]) {
  if (rows.length === 0) {
    return <p className="muted">No release comparison data available yet.</p>;
  }

  return (
    <div className="table-wrapper release-comparison-wrapper">
      <table className="issues-table release-comparison-table">
        <thead>
          <tr>
            <th>Release</th>
            <th>Confidence</th>
            <th>Blockers</th>
            <th>Bugs</th>
            <th>Reopen</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.release_id}>
              <td>
                <span>{row.name}</span>
                {row.is_unreleased ? <span className="comparison-status-note">Unreleased</span> : null}
              </td>
              <td>{formatNullablePct(row.confidence_score)}</td>
              <td>{formatNullableNumber(row.blockers)}</td>
              <td>{formatNullableNumber(row.bugs)}</td>
              <td>{formatNullablePct(row.reopen_rate_pct)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

async function loadReleaseComparisonRow(release: Release): Promise<ReleaseComparisonRow> {
  const [metricsResponse, signalResponse] = await Promise.all([
    apiClient.getMetrics(release.release_id),
    apiClient.getSignal(release.release_id),
  ]);
  const metrics: ReleaseMetricsResponse["metrics"] = metricsResponse.metrics;

  return {
    release_id: release.release_id,
    name: release.name,
    confidence_score: signalResponse.confidence_score,
    blockers: metrics.open_blockers,
    bugs: metrics.open_high_severity_bugs,
    reopen_rate_pct: metrics.reopen_rate_pct,
    is_unreleased: isUnreleasedRelease(release),
  };
}

export function ChartsPanel({
  charts,
  signal,
  metrics,
  releases,
  selectedProjectKey,
  selectedReleaseName,
  refreshNonce,
  isLoading,
}: ChartsPanelProps) {
  const confidenceRows = useMemo(() => buildSingleMetricRows(charts, "confidence_score"), [charts]);
  const gateRows = useMemo(() => buildSingleMetricRows(charts, "gates_passed_count"), [charts]);
  const readinessRows = useMemo(() => buildSingleMetricRows(charts, "readiness_pct"), [charts]);
  const riskContributionRows = useMemo(() => buildRiskContributionRows(signal), [signal]);
  const blockerAgingRows = useMemo(() => buildBlockerAgingRows(signal?.risk_aging.blockers), [signal]);
  const recentReleases = useMemo(() => getRecentReleases(releases, selectedProjectKey), [releases, selectedProjectKey]);
  const [snapshotBaseline, setSnapshotBaseline] = useState<SnapshotBaseline>("previous");
  const [snapshotComparison, setSnapshotComparison] = useState<SnapshotComparisonResponse | null>(null);
  const [snapshotHistory, setSnapshotHistory] = useState<SnapshotChangeHistoryResponse | null>(null);
  const [isLoadingSnapshotChanges, setIsLoadingSnapshotChanges] = useState(false);
  const [snapshotChangeError, setSnapshotChangeError] = useState<string | null>(null);
  const [comparisonRows, setComparisonRows] = useState<ReleaseComparisonRow[]>([]);
  const [isLoadingComparison, setIsLoadingComparison] = useState(false);
  const [comparisonError, setComparisonError] = useState<string | null>(null);
  const [isChartsExpanded, setIsChartsExpanded] = useState(true);

  useEffect(() => {
    const releaseId = charts?.release_id;
    if (!releaseId) {
      setSnapshotComparison(null);
      setSnapshotHistory(null);
      return;
    }
    const activeReleaseId = releaseId;

    let isActive = true;

    async function loadSnapshotChanges() {
      setIsLoadingSnapshotChanges(true);
      setSnapshotChangeError(null);
      try {
        const [comparison, history] = await Promise.all([
          apiClient.getReleaseSnapshotComparison(activeReleaseId, snapshotBaseline),
          apiClient.getReleaseSnapshotChangeHistory(activeReleaseId),
        ]);
        if (isActive) {
          setSnapshotComparison(comparison);
          setSnapshotHistory(history);
        }
      } catch (error) {
        if (isActive) {
          setSnapshotChangeError(error instanceof Error ? error.message : "Failed to load snapshot changes.");
          setSnapshotComparison(null);
          setSnapshotHistory(null);
        }
      } finally {
        if (isActive) {
          setIsLoadingSnapshotChanges(false);
        }
      }
    }

    void loadSnapshotChanges();

    return () => {
      isActive = false;
    };
  }, [charts?.release_id, snapshotBaseline, refreshNonce]);

  useEffect(() => {
    if (recentReleases.length === 0) {
      setComparisonRows([]);
      return;
    }

    let isActive = true;

    async function loadComparison() {
      setIsLoadingComparison(true);
      setComparisonError(null);
      try {
        const rows = await Promise.all(recentReleases.map(loadReleaseComparisonRow));
        if (isActive) {
          setComparisonRows(rows);
        }
      } catch (error) {
        if (isActive) {
          setComparisonError(error instanceof Error ? error.message : "Failed to load release comparison.");
          setComparisonRows([]);
        }
      } finally {
        if (isActive) {
          setIsLoadingComparison(false);
        }
      }
    }

    void loadComparison();

    return () => {
      isActive = false;
    };
  }, [recentReleases, refreshNonce]);

  return (
    <section className="panel charts-panel">
      <div className="panel-heading">
        <h2>Release Charts</h2>
        <div className="panel-heading-actions">
          {charts ? <span className="muted">Snapshots {charts.point_count}</span> : null}
          <button
            type="button"
            className="secondary-button compact-button"
            aria-expanded={isChartsExpanded}
            onClick={() => setIsChartsExpanded((current) => !current)}
          >
            {isChartsExpanded ? "Minimize" : "Expand"}
          </button>
        </div>
      </div>
      {isChartsExpanded ? (
        <>
          {isLoading ? <p className="muted">Loading charts...</p> : null}

          <SnapshotChangePanel
            context="release"
            comparison={snapshotComparison}
            history={snapshotHistory}
            baseline={snapshotBaseline}
            isLoading={isLoadingSnapshotChanges}
            error={snapshotChangeError}
            onBaselineChange={setSnapshotBaseline}
          />

          {signal?.biggest_driver ? (
            <BiggestDriverCard driver={signal.biggest_driver} heading="Biggest Confidence Drag" />
          ) : null}
          {metrics ? (
            <RecommendationsPanel
              recommendations={metrics.recommendations}
              title="Report Recommendations"
            />
          ) : null}

          <div className="chart-section-heading">
            <div>
              <h3>Confidence Evolution</h3>
              <p className="chart-section-subtitle">
                Tracks how release confidence has changed across collected snapshots.
              </p>
            </div>
            {selectedReleaseName ? <span className="muted">{selectedReleaseName}</span> : null}
          </div>
          <MetricLineChart
            data={confidenceRows}
            lines={[
              {
                key: "value",
                label: chartMetricLabels.confidence_score,
                color: MetricColors.sprintConfidence,
              },
            ]}
            formatter={(value) => formatPercentage(value)}
            yDomain={[0, 100]}
            yTickFormatter={(value) => `${value}%`}
            empty={!isLoading && confidenceRows.length === 0}
            emptyMessage="No confidence history available yet."
            loading={isLoading}
          />

          <div className="chart-section-heading">
            <div>
              <h3>Risk Breakdown</h3>
              <p className="chart-section-subtitle">
                Shows which measured risks are contributing most to the current release signal.
              </p>
            </div>
            {riskContributionRows.length > 0 ? <span className="muted">Contribution %</span> : null}
          </div>
          <MetricHorizontalBarChart
            data={riskContributionRows}
            barKey="contribution_pct"
            barLabel="Risk contribution"
            cellColors={(row) => riskMetricColors[String(row.metric_name)] ?? MetricColors.neutralRisk}
            formatter={(value) => formatPercentage(value)}
            empty={!signal || riskContributionRows.length === 0}
            emptyMessage="No active risk contribution."
          />

          <div className="chart-section-heading">
            <div>
              <h3>Quality Gates Pass Trend</h3>
              <p className="chart-section-subtitle">
                Tracks how many release gates are passing as the release moves toward readiness.
              </p>
            </div>
            {charts ? <span className="muted">Out of {charts.release_gates_total}</span> : null}
          </div>
          <MetricLineChart
            data={gateRows}
            lines={[
              {
                key: "value",
                label: chartMetricLabels.gates_passed_count,
                color: MetricColors.gatesPassed,
              },
            ]}
            formatter={(value) => `${Math.round(value)}/${charts?.release_gates_total ?? 0}`}
            yDomain={[0, charts?.release_gates_total ?? 5]}
            yTickFormatter={(value) => String(Math.round(value))}
            empty={!isLoading && gateRows.length === 0}
            emptyMessage="No gate pass history available yet."
            loading={isLoading}
          />

          <div className="chart-section-heading">
            <div>
              <h3>Readiness Trend</h3>
              <p className="chart-section-subtitle">
                Shows the percentage of release readiness checks currently satisfied over time.
              </p>
            </div>
          </div>
          <MetricLineChart
            data={readinessRows}
            lines={[
              {
                key: "value",
                label: chartMetricLabels.readiness_pct,
                color: MetricColors.readiness,
              },
            ]}
            formatter={(value) => formatPercentage(value)}
            yDomain={[0, 100]}
            yTickFormatter={(value) => `${value}%`}
            empty={!isLoading && readinessRows.length === 0}
            emptyMessage="No readiness history available yet."
            loading={isLoading}
          />

          <div className="chart-section-heading">
            <div>
              <h3>Blocker Aging</h3>
              <p className="chart-section-subtitle">
                Groups open blockers by age so long-running impediments are easier to spot.
              </p>
            </div>
            {signal?.risk_aging.as_of ? (
              <span className="muted">As of {new Date(signal.risk_aging.as_of).toLocaleDateString()}</span>
            ) : null}
          </div>
          <MetricBarChart
            data={blockerAgingRows}
            barKey="count"
            barLabel="Blockers"
            barColor={MetricColors.blockers}
            height={240}
            formatter={(value) => String(Math.round(value))}
            empty={!signal || (signal.risk_aging.blockers.tickets ?? []).length === 0}
            emptyMessage="No blockers."
          />

          <div className="chart-section-heading">
            <div>
              <h3>Release Comparison Dashboard</h3>
              <p className="chart-section-subtitle">
                Compares recent releases across confidence, blockers, bugs, and reopen risk.
              </p>
            </div>
            {comparisonRows.length > 0 ? <span className="muted">Last {comparisonRows.length}</span> : null}
          </div>
          {isLoadingComparison ? <p className="muted">Loading release comparison...</p> : null}
          {comparisonError ? <p className="error-text">{comparisonError}</p> : null}
          {!isLoadingComparison && !comparisonError ? renderComparisonTable(comparisonRows) : null}
        </>
      ) : null}
    </section>
  );
}
