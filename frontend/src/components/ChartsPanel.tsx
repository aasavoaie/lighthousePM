import { useEffect, useMemo, useState } from "react";

import { apiClient } from "../api/client";
import type { Release, ReleaseChartsResponse } from "../api/types";
import {
  MetricColors,
  MetricLineChart,
  MetricBarChart,
  formatPercentage,
} from "./ChartComponents";

interface ChartsPanelProps {
  charts: ReleaseChartsResponse | null;
  releases: Release[];
  refreshNonce: number;
  isLoading: boolean;
}

type StoryPointRow = {
  release_id: string;
  name: string;
  story_points: number;
  is_unreleased: boolean;
};

type ReleaseSignalTrendRow = {
  release_id: string;
  release_name: string;
  signal: string;
};

type SignalChartRow = {
  name: string;
  signal_score: number;
  signal: string;
};

const issuePageSize = 100;

const chartLines = [
  { key: "open_blockers", color: MetricColors.blockers, label: "Open blockers" },
  { key: "open_high_severity_bugs", color: MetricColors.bugs, label: "High-severity bugs" },
  { key: "scope_completed_pct", color: MetricColors.scopeCompleted, label: "Scope completed %" },
];

function buildChartRows(charts: ReleaseChartsResponse | null) {
  if (!charts) {
    return [];
  }

  const rows = new Map<string, Record<string, number | string | null>>();
  for (const metricName of charts.metric_names) {
    const points = charts.series[metricName as keyof typeof charts.series];
    for (const point of points) {
      const existing = rows.get(point.snapshot_at) ?? {
        snapshot_at: new Date(point.snapshot_at).toLocaleDateString(),
      };
      existing[metricName] = point.value;
      rows.set(point.snapshot_at, existing);
    }
  }
  return Array.from(rows.entries())
    .sort(([left], [right]) => left.localeCompare(right))
    .map(([, value]) => value);
}

function releaseSortTime(release: Release) {
  const primaryDate = release.release_date ?? release.created_at;
  const parsed = Date.parse(primaryDate);
  return Number.isFinite(parsed) ? parsed : 0;
}

function getRecentReleases(releases: Release[]) {
  return [...releases]
    .sort((left, right) => releaseSortTime(right) - releaseSortTime(left))
    .slice(0, 5)
    .reverse();
}

function signalHealthScore(signalValue: string | null): number | null {
  if (signalValue === "GREEN") {
    return 3;
  }
  if (signalValue === "YELLOW") {
    return 2;
  }
  if (signalValue === "RED") {
    return 1;
  }
  return null;
}

function buildSignalChartRows(rows: ReleaseSignalTrendRow[]): SignalChartRow[] {
  return rows.map((row) => ({
    name: row.release_name,
    signal_score: signalHealthScore(row.signal) ?? 0,
    signal: row.signal,
  }));
}

function getSignalColor(signal: string) {
  if (signal === "GREEN") {
    return "#237445";
  }
  if (signal === "YELLOW") {
    return "#e48f00";
  }
  if (signal === "RED") {
    return "#c43c2d";
  }
  return MetricColors.sprintConfidence;
}

function isUnreleasedRelease(release: Release) {
  return (release.status ?? "").trim().toLowerCase() !== "released";
}

export function ChartsPanel({ charts, releases, refreshNonce, isLoading }: ChartsPanelProps) {
  const rows = buildChartRows(charts);
  const recentReleases = useMemo(() => getRecentReleases(releases), [releases]);
  const [storyPointRows, setStoryPointRows] = useState<StoryPointRow[]>([]);
  const [isLoadingStoryPoints, setIsLoadingStoryPoints] = useState(false);
  const [storyPointError, setStoryPointError] = useState<string | null>(null);
  const [signalTrendRows, setSignalTrendRows] = useState<ReleaseSignalTrendRow[]>([]);
  const [signalTrendChartRows, setSignalTrendChartRows] = useState<SignalChartRow[]>([]);
  const [isLoadingSignalTrend, setIsLoadingSignalTrend] = useState(false);
  const [signalTrendError, setSignalTrendError] = useState<string | null>(null);

  useEffect(() => {
    if (recentReleases.length === 0) {
      setStoryPointRows([]);
      return;
    }

    let isActive = true;

    async function loadStoryPoints() {
      setIsLoadingStoryPoints(true);
      setStoryPointError(null);
      try {
        const rows = await Promise.all(
          recentReleases.map(async (release) => {
            let allStoryPoints = 0;
            let fetchedCount = 0;
            let total = 0;

            while (true) {
              const response = await apiClient.getReleaseIssues(release.release_id, fetchedCount, issuePageSize);
              total = response.total;
              for (const issue of response.items) {
                allStoryPoints += issue.story_points ?? 0;
              }

              fetchedCount += response.items.length;
              if (fetchedCount >= total || response.items.length === 0) {
                break;
              }
            }

            return {
              release_id: release.release_id,
              name: release.name,
              story_points: Number(allStoryPoints.toFixed(2)),
              is_unreleased: isUnreleasedRelease(release),
            };
          })
        );

        if (isActive) {
          setStoryPointRows(rows);
        }
      } catch (error) {
        if (isActive) {
          setStoryPointError(error instanceof Error ? error.message : "Failed to load release story points.");
        }
      } finally {
        if (isActive) {
          setIsLoadingStoryPoints(false);
        }
      }
    }

    void loadStoryPoints();

    return () => {
      isActive = false;
    };
  }, [recentReleases, refreshNonce]);

  useEffect(() => {
    if (recentReleases.length === 0) {
      setSignalTrendRows([]);
      setSignalTrendChartRows([]);
      return;
    }

    let isActive = true;

    async function loadSignalTrend() {
      setIsLoadingSignalTrend(true);
      setSignalTrendError(null);

      try {
        const rows = await Promise.all(
          recentReleases.map(async (release) => {
            const response = await apiClient.getSignal(release.release_id);
            return {
              release_id: release.release_id,
              release_name: release.name,
              signal: response.signal ?? "UNKNOWN",
            };
          })
        );

        if (isActive) {
          const validRows = rows.filter((row) => row.signal !== "UNKNOWN");
          setSignalTrendRows(validRows);
          setSignalTrendChartRows(buildSignalChartRows(validRows));
        }
      } catch (error) {
        if (isActive) {
          setSignalTrendError(error instanceof Error ? error.message : "Failed to load signal trend.");
          setSignalTrendRows([]);
          setSignalTrendChartRows([]);
        }
      } finally {
        if (isActive) {
          setIsLoadingSignalTrend(false);
        }
      }
    }

    void loadSignalTrend();

    return () => {
      isActive = false;
    };
  }, [recentReleases, refreshNonce]);

  return (
    <section className="panel charts-panel">
      <div className="panel-heading">
        <h2>Release events</h2>
        {charts ? <span className="muted">Snapshots {charts.point_count}</span> : null}
      </div>
      {isLoading ? <p className="muted">Loading charts...</p> : null}
      {!isLoading && rows.length === 0 ? <p className="muted">No chart data available yet.</p> : null}
      {!isLoading && rows.length > 0 ? (
        <MetricLineChart
          data={rows}
          lines={chartLines}
          dataKey="snapshot_at"
          formatter={(value, name) => {
            if (name === "scope_completed_pct" || name === "open_high_severity_bugs" || name === "open_blockers") {
              return String(value);
            }
            return formatPercentage(value);
          }}
        />
      ) : null}

      <div className="chart-section-heading">
        <h3>Signal trend (recent releases)</h3>
        {signalTrendChartRows.length > 0 ? <span className="muted">Last {signalTrendChartRows.length}</span> : null}
      </div>
      {signalTrendError ? <p className="error-text">{signalTrendError}</p> : null}
      {!signalTrendError ? (
        <MetricBarChart
          data={signalTrendChartRows}
          barKey="signal_score"
          barLabel="Signal health"
          barColor={MetricColors.sprintConfidence}
          cellColors={(row) => getSignalColor((row as SignalChartRow).signal)}
          height={240}
          dataKey="name"
          formatter={(value) => {
            const valueMap: Record<number, string> = { 1: "RED", 2: "YELLOW", 3: "GREEN" };
            return valueMap[Math.round(value)] || String(value);
          }}
          loading={isLoadingSignalTrend}
          empty={signalTrendChartRows.length === 0}
          emptyMessage="Loading signal trend..."
        />
      ) : null}

      <div className="chart-section-heading">
        <h3>Story points in every release</h3>
        {storyPointRows.length > 0 ? <span className="muted">Last {storyPointRows.length}</span> : null}
      </div>
      <div className="chart-legend-note" aria-label="Release status color legend">
        <span className="chart-legend-swatch unreleased" aria-hidden="true" />
        <span>All releases in this color are not released yet.</span>
      </div>
      {storyPointError ? <p className="error-text">{storyPointError}</p> : null}
      {!isLoadingStoryPoints && !storyPointError ? (
        <MetricBarChart
          data={storyPointRows}
          barKey="story_points"
          barLabel="Story points"
          barColor={MetricColors.releasedStoryPoints}
          cellColors={(row) => {
            const storyRow = row as StoryPointRow;
            return storyRow.is_unreleased
              ? MetricColors.unreleasedStoryPoints
              : MetricColors.releasedStoryPoints;
          }}
          loading={isLoadingStoryPoints}
          empty={storyPointRows.length === 0}
          emptyMessage="No release story point data available yet."
        />
      ) : null}
    </section>
  );
}
