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

import type { ReleaseChartsResponse } from "../api/types";

interface ChartsPanelProps {
  charts: ReleaseChartsResponse | null;
  isLoading: boolean;
}

type SprintVelocityChartRow = {
  sprint_id: string;
  sprint_name: string;
  completed_at: string | null;
  velocity: number;
  state: string;
  note: string | null;
};

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

function buildVelocityRows(charts: ReleaseChartsResponse | null): SprintVelocityChartRow[] {
  if (!charts) {
    return [];
  }
  return charts.sprint_velocity.points.map((point) => ({
    sprint_id: point.sprint_id,
    sprint_name: point.sprint_name,
    completed_at: point.completed_at,
    velocity: point.velocity,
    state: point.state,
    note: point.note,
  }));
}

function VelocityTooltip({
  active,
  payload,
  label,
}: {
  active?: boolean;
  payload?: Array<{ value?: number | string | null; payload?: SprintVelocityChartRow }>;
  label?: string;
}) {
  if (!active || !payload || payload.length === 0) {
    return null;
  }

  const row = payload[0]?.payload;
  if (!row) {
    return null;
  }

  return (
    <div className="chart-tooltip">
      <strong>{label}</strong>
      <p>Velocity: {row.velocity.toFixed(2)}</p>
      {row.note ? <p className="chart-tooltip-note">{row.note}</p> : null}
    </div>
  );
}

const metricDefinitions: Record<
  string,
  { label: string; color: string }
> = {
  open_blockers: { label: "Open blockers", color: "#c43c2d" },
  open_high_severity_bugs: { label: "High-severity bugs", color: "#e48f00" },
  scope_completed_pct: { label: "Scope completed %", color: "#0b6bcb" },
  scope_churn_7d_pct: { label: "Scope churn (7d) %", color: "#6b8e23" },
  median_cycle_time_days: { label: "Median cycle time (days)", color: "#6f42c1" },
  reopen_rate_pct: { label: "Reopen rate %", color: "#10a37f" },
};

function buildChartSeries(charts: ReleaseChartsResponse | null) {
  if (!charts) {
    return [];
  }

  return charts.metric_names.map((metricName) => ({
    key: metricName,
    label: metricDefinitions[metricName]?.label ?? metricName,
    color: metricDefinitions[metricName]?.color ?? "#0b6bcb",
  }));
}

export function ChartsPanel({ charts, isLoading }: ChartsPanelProps) {
  const rows = buildChartRows(charts);
  const velocityRows = buildVelocityRows(charts);
  const chartSeries = buildChartSeries(charts);
  const showVelocitySection = !isLoading && charts !== null;

  return (
    <section className="panel charts-panel">
      <div className="panel-heading">
        <h2>Charts</h2>
        {charts ? <span className="muted">Snapshots {charts.point_count}</span> : null}
      </div>
      {isLoading ? <p className="muted">Loading charts...</p> : null}
      {!isLoading && !charts ? <p className="muted">No chart data available yet.</p> : null}
      {!isLoading && rows.length > 0 ? (
        <div className="chart-section">
          <h3>Release Metrics</h3>
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
        </div>
      ) : null}
      {showVelocitySection ? (
        <div className="chart-section">
          <div className="panel-heading chart-subheading">
            <h3>Sprint Velocity</h3>
            {charts ? <span className="muted">Sprints {charts.sprint_velocity.point_count}</span> : null}
          </div>
          {velocityRows.length === 0 ? <p className="muted">No sprint velocity data available yet.</p> : null}
          {velocityRows.length > 0 ? (
            <div className="chart-wrapper">
              <ResponsiveContainer width="100%" height={320}>
                <BarChart data={velocityRows}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="sprint_name" interval={0} />
                  <YAxis />
                  <Tooltip content={<VelocityTooltip />} />
                  <Legend />
                  <Bar dataKey="velocity" name="Completed points">
                    {velocityRows.map((row) => (
                      <Cell key={row.sprint_id} fill={row.note ? "#2d7d46" : "#0b6bcb"} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>
          ) : null}
        </div>
      ) : null}
    </section>
  );
}
