/**
 * Reusable Recharts components for consistent dashboard visualization
 * 
 * All charts follow the project philosophy:
 * - Deterministic (data from backend API)
 * - Simple (single ResponsiveContainer pattern)
 * - Clear (consistent colors and styling)
 * - Trustworthy (exact values in tooltips)
 */

import {
  Bar,
  BarChart as RechartsBarChart,
  CartesianGrid,
  Cell,
  Legend as RechartsLegend,
  Line,
  LineChart as RechartsLineChart,
  ResponsiveContainer,
  Tooltip as RechartsTooltip,
  XAxis,
  YAxis,
  type TooltipProps,
} from "recharts";

/**
 * Metric color palette
 * Matches AGENTS.md principle: clarity over cleverness
 */
export const MetricColors = {
  blockers: "#c43c2d",
  bugs: "#e48f00",
  scopeCompleted: "#0b6bcb",
  completedTickets: "#237445",
  scopeChurn: "#6f42c1",
  cycleTime: "#237445",
  reopenRate: "#9f6a00",
  sprintConfidence: "#237445",
  committedScope: "#0b6bcb",
  completedScope: "#237445",
  releasedStoryPoints: "#0b6bcb",
  unreleasedStoryPoints: "#e48f00",
  closedSprintStoryPoints: "#0b6bcb",
  notClosedSprintStoryPoints: "#e48f00",
} as const;

/**
 * Standard tooltip for all charts
 * Shows exact values with appropriate formatting
 */
interface CustomTooltipProps extends TooltipProps<number, string> {
  formatter?: (value: number, name: string) => string;
}

export function CustomChartTooltip({ active, payload, formatter }: CustomTooltipProps) {
  if (!active || !payload) {
    return null;
  }

  return (
    <div className="recharts-tooltip-wrapper">
      {payload.map((entry, index) => (
        <div key={index} className="recharts-tooltip-item" style={{ color: entry.color }}>
          <span className="recharts-tooltip-label">{entry.name}: </span>
          <span className="recharts-tooltip-value">
            {formatter ? formatter(Number(entry.value), entry.name as string) : entry.value}
          </span>
        </div>
      ))}
    </div>
  );
}

/**
 * Reusable line chart for metrics over time
 * Props match Recharts LineChart with standardized styling
 */
interface MetricLineChartProps {
  data: Array<Record<string, unknown>>;
  lines: Array<{
    key: string;
    label: string;
    color: string;
  }>;
  height?: number;
  dataKey?: string;
  formatter?: (value: number, name: string) => string;
  loading?: boolean;
  empty?: boolean;
  emptyMessage?: string;
}

export function MetricLineChart({
  data,
  lines,
  height = 320,
  dataKey = "snapshot_at",
  formatter,
  loading = false,
  empty = false,
  emptyMessage = "No data available",
}: MetricLineChartProps) {
  if (loading) {
    return <p className="muted">Loading chart...</p>;
  }

  if (empty) {
    return <p className="muted">{emptyMessage}</p>;
  }

  return (
    <div className="chart-wrapper">
      <ResponsiveContainer width="100%" height={height}>
        <RechartsLineChart data={data}>
          <CartesianGrid strokeDasharray="3 3" />
          <XAxis dataKey={dataKey} />
          <YAxis />
          <RechartsTooltip content={<CustomChartTooltip formatter={formatter} />} />
          <RechartsLegend />
          {lines.map((line) => (
            <Line
              key={line.key}
              type="monotone"
              dataKey={line.key}
              name={line.label}
              stroke={line.color}
              strokeWidth={2}
              dot={false}
            />
          ))}
        </RechartsLineChart>
      </ResponsiveContainer>
    </div>
  );
}

/**
 * Reusable bar chart for categorical metrics
 * Props match Recharts BarChart with standardized styling
 */
interface MetricBarChartProps {
  data: Array<Record<string, unknown>>;
  barKey: string;
  barLabel: string;
  barColor?: string;
  cellColors?: (data: Record<string, unknown>) => string;
  height?: number;
  dataKey?: string;
  formatter?: (value: number, name: string) => string;
  loading?: boolean;
  empty?: boolean;
  emptyMessage?: string;
}

export function MetricBarChart({
  data,
  barKey,
  barLabel,
  barColor = MetricColors.releasedStoryPoints,
  cellColors,
  height = 320,
  dataKey = "name",
  formatter,
  loading = false,
  empty = false,
  emptyMessage = "No data available",
}: MetricBarChartProps) {
  if (loading) {
    return <p className="muted">Loading chart...</p>;
  }

  if (empty) {
    return <p className="muted">{emptyMessage}</p>;
  }

  return (
    <div className="chart-wrapper">
      <ResponsiveContainer width="100%" height={height}>
        <RechartsBarChart data={data}>
          <CartesianGrid strokeDasharray="3 3" />
          <XAxis dataKey={dataKey} />
          <YAxis />
          <RechartsTooltip content={<CustomChartTooltip formatter={formatter} />} />
          <RechartsLegend />
          <Bar dataKey={barKey} name={barLabel} fill={barColor} radius={[6, 6, 0, 0]}>
            {cellColors && data
              ? (data as Record<string, unknown>[]).map((row, index) => (
                  <Cell key={index} fill={cellColors(row)} />
                ))
              : null}
          </Bar>
        </RechartsBarChart>
      </ResponsiveContainer>
    </div>
  );
}

interface MetricMultiBarChartProps {
  data: Array<Record<string, unknown>>;
  bars: Array<{ key: string; label: string; color: string }>;
  height?: number;
  dataKey?: string;
  formatter?: (value: number, name: string) => string;
  loading?: boolean;
  empty?: boolean;
  emptyMessage?: string;
}

export function MetricMultiBarChart({
  data,
  bars,
  height = 320,
  dataKey = "name",
  formatter,
  loading = false,
  empty = false,
  emptyMessage = "No data available",
}: MetricMultiBarChartProps) {
  if (loading) {
    return <p className="muted">Loading chart...</p>;
  }

  if (empty) {
    return <p className="muted">{emptyMessage}</p>;
  }

  return (
    <div className="chart-wrapper">
      <ResponsiveContainer width="100%" height={height}>
        <RechartsBarChart data={data}>
          <CartesianGrid strokeDasharray="3 3" />
          <XAxis dataKey={dataKey} />
          <YAxis />
          <RechartsTooltip content={<CustomChartTooltip formatter={formatter} />} />
          <RechartsLegend />
          {bars.map((bar) => (
            <Bar
              key={bar.key}
              dataKey={bar.key}
              name={bar.label}
              fill={bar.color}
              radius={[6, 6, 0, 0]}
            />
          ))}
        </RechartsBarChart>
      </ResponsiveContainer>
    </div>
  );
}
interface MetricSparklineProps {
  data: Array<Record<string, unknown>>;
  valueKey: string;
  lineColor: string;
  height?: number;
  formatter?: (value: number, name: string) => string;
  loading?: boolean;
  empty?: boolean;
  emptyMessage?: string;
}

export function MetricSparkline({
  data,
  valueKey,
  lineColor,
  height = 68,
  formatter,
  loading = false,
  empty = false,
  emptyMessage = "No trend data available",
}: MetricSparklineProps) {
  if (loading) {
    return <p className="muted">Loading trend...</p>;
  }

  if (empty) {
    return <p className="metric-sparkline-empty muted">{emptyMessage}</p>;
  }

  return (
    <div className="metric-sparkline">
      <ResponsiveContainer width="100%" height={height}>
        <RechartsLineChart data={data}>
          <CartesianGrid vertical={false} strokeDasharray="3 3" stroke="#e8eef5" />
          <XAxis dataKey="snapshot_at" hide />
          <YAxis hide domain={["auto", "auto"]} />
          <RechartsTooltip content={<CustomChartTooltip formatter={formatter} />} />
          <Line
            type="monotone"
            dataKey={valueKey}
            stroke={lineColor}
            strokeWidth={2}
            dot={false}
            activeDot={{ r: 3 }}
          />
        </RechartsLineChart>
      </ResponsiveContainer>
    </div>
  );
}
/**
 * Helper formatter for percentage values
 */
export function formatPercentage(value: number): string {
  return `${value.toFixed(2)}%`;
}

/**
 * Helper formatter for whole numbers
 */
export function formatWholeNumber(value: number): string {
  return String(Math.round(value));
}

/**
 * Helper formatter for decimal numbers with 2 places
 */
export function formatDecimal(value: number): string {
  return value.toFixed(2);
}
