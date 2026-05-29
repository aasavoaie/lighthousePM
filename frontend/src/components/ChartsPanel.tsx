import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { useEffect, useMemo, useState } from "react";

import { apiClient } from "../api/client";
import type { Release, ReleaseChartsResponse } from "../api/types";

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

const issuePageSize = 100;
const releasedStoryPointColor = "#0b6bcb";
const unreleasedStoryPointColor = "#e48f00";

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

const chartSeries = [
  { key: "open_blockers", color: "#c43c2d", label: "Open blockers" },
  { key: "open_high_severity_bugs", color: "#e48f00", label: "High-severity bugs" },
  { key: "scope_completed_pct", color: "#0b6bcb", label: "Scope completed %" },
];

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

function isUnreleasedRelease(release: Release) {
  return (release.status ?? "").trim().toLowerCase() !== "released";
}

export function ChartsPanel({ charts, releases, refreshNonce, isLoading }: ChartsPanelProps) {
  const rows = buildChartRows(charts);
  const recentReleases = useMemo(() => getRecentReleases(releases), [releases]);
  const [storyPointRows, setStoryPointRows] = useState<StoryPointRow[]>([]);
  const [isLoadingStoryPoints, setIsLoadingStoryPoints] = useState(false);
  const [storyPointError, setStoryPointError] = useState<string | null>(null);

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

  return (
    <section className="panel charts-panel">
      <div className="panel-heading">
        <h2>Release events</h2>
        {charts ? <span className="muted">Snapshots {charts.point_count}</span> : null}
      </div>
      {isLoading ? <p className="muted">Loading charts...</p> : null}
      {!isLoading && rows.length === 0 ? <p className="muted">No chart data available yet.</p> : null}
      {!isLoading && rows.length > 0 ? (
        <div className="chart-wrapper">
          <ResponsiveContainer width="100%" height={320}>
            <LineChart data={rows}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="snapshot_at" />
              <YAxis />
              <Tooltip />
              <Legend />
              {chartSeries.map((series) => (
                <Line
                  key={series.key}
                  type="monotone"
                  dataKey={series.key}
                  name={series.label}
                  stroke={series.color}
                  strokeWidth={2}
                  dot={false}
                />
              ))}
            </LineChart>
          </ResponsiveContainer>
        </div>
      ) : null}

      <div className="chart-section-heading">
        <h3>Story points in every release</h3>
        {storyPointRows.length > 0 ? <span className="muted">Last {storyPointRows.length}</span> : null}
      </div>
      <div className="chart-legend-note" aria-label="Release status color legend">
        <span className="chart-legend-swatch unreleased" aria-hidden="true" />
        <span>All releases in this color are not released yet.</span>
      </div>
      {isLoadingStoryPoints ? <p className="muted">Loading story points...</p> : null}
      {storyPointError ? <p className="error-text">{storyPointError}</p> : null}
      {!isLoadingStoryPoints && !storyPointError && storyPointRows.length === 0 ? (
        <p className="muted">No release story point data available yet.</p>
      ) : null}
      {!isLoadingStoryPoints && !storyPointError && storyPointRows.length > 0 ? (
        <div className="chart-wrapper">
          <ResponsiveContainer width="100%" height={320}>
            <BarChart data={storyPointRows}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="name" />
              <YAxis />
              <Tooltip />
              <Legend />
              <Bar dataKey="story_points" name="Story points" fill={releasedStoryPointColor} radius={[6, 6, 0, 0]}>
                {storyPointRows.map((row) => (
                  <Cell
                    key={row.release_id}
                    fill={row.is_unreleased ? unreleasedStoryPointColor : releasedStoryPointColor}
                  />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      ) : null}
    </section>
  );
}
