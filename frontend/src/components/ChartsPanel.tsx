import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import type { ReleaseChartsResponse } from "../api/types";

interface ChartsPanelProps {
  charts: ReleaseChartsResponse | null;
  isLoading: boolean;
}

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

export function ChartsPanel({ charts, isLoading }: ChartsPanelProps) {
  const rows = buildChartRows(charts);

  return (
    <section className="panel charts-panel">
      <div className="panel-heading">
        <h2>Charts</h2>
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
    </section>
  );
}