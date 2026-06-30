import type { DeliveryConfidenceDetail, SprintMetricValues, SprintMetricsResponse } from "../api/types";
import type { MetricStatus } from "./MetricCards";
import { getMetricStatus, hasSprintStoryPoints } from "./sprintMetrics";

export type RiskHeatmapStatus = "healthy" | "watch" | "risk" | "critical" | "neutral";

export const confidenceStatusThresholds = {
  healthy: 80,
  watch: 60,
  risk: 40,
} as const;

export const scopeCreepStatusThresholds = {
  critical: 20,
  watch: 10,
} as const;

export interface SprintChartSource {
  sprint_id: string;
  name: string;
  is_not_closed: boolean;
  metrics: SprintMetricsResponse;
}

export interface SprintChartHistoryPoint {
  [key: string]: string | number | boolean | null;
  sprint_id: string;
  name: string;
  is_not_closed: boolean;
  delivery_confidence: number | null;
  confidence_delta: number | null;
  progress_alignment: number | null;
  velocity_fit: number | null;
  blocker_health: number | null;
  scope_stability: number | null;
  committed_story_points: number | null;
  completed_story_points: number | null;
  reliability_pct: number | null;
  predictability_avg: number | null;
  scope_change_count: number;
  scope_creep_pct: number | null;
  scope_added_count: number;
  scope_removed_count: number;
  net_scope_change: number;
  open_high_severity_bugs: number | null;
  bugs_created_during_sprint: number | null;
  reopen_rate_pct: number | null;
  median_cycle_time_days: number | null;
  delivery_status: RiskHeatmapStatus;
  quality_status: RiskHeatmapStatus;
  flow_status: RiskHeatmapStatus;
  risk_status: RiskHeatmapStatus;
}

export type HeatmapGroup = "Delivery" | "Quality" | "Flow" | "Risk";

export interface RiskHeatmapCell {
  sprint_id: string;
  sprint_name: string;
  group: HeatmapGroup;
  status: RiskHeatmapStatus;
}

export function calculateReliabilityPct(committedStoryPoints: number, completedStoryPoints: number) {
  if (committedStoryPoints <= 0) {
    return null;
  }
  return Number(((completedStoryPoints / committedStoryPoints) * 100).toFixed(2));
}

export function getConfidenceStatusLevel(confidence: number): RiskHeatmapStatus {
  if (confidence >= confidenceStatusThresholds.healthy) {
    return "healthy";
  }
  if (confidence >= confidenceStatusThresholds.watch) {
    return "watch";
  }
  return confidence >= confidenceStatusThresholds.risk ? "risk" : "critical";
}

export function getSprintGroupHealthStatus(statuses: RiskHeatmapStatus[]): RiskHeatmapStatus {
  if (statuses.some((status) => status === "critical")) {
    return "critical";
  }
  if (statuses.some((status) => status === "risk")) {
    return "risk";
  }
  if (statuses.some((status) => status === "watch")) {
    return "watch";
  }
  if (statuses.some((status) => status === "healthy")) {
    return "healthy";
  }
  return "neutral";
}

function metricStatusToHeatmap(status: MetricStatus): RiskHeatmapStatus {
  if (status === "good") {
    return "healthy";
  }
  if (status === "warning") {
    return "watch";
  }
  if (status === "critical") {
    return "critical";
  }
  return "neutral";
}

export function calculateMovingAverage(values: Array<number | null>, windowSize: number) {
  return values.map((_, index) => {
    const windowValues = values.slice(Math.max(0, index - windowSize + 1), index + 1).filter((value): value is number => value !== null);
    if (windowValues.length < windowSize) {
      return null;
    }
    return Number((windowValues.reduce((sum, value) => sum + value, 0) / windowValues.length).toFixed(2));
  });
}

export function hasChartData<T>(rows: T[], keys: Array<keyof T>) {
  return rows.some((row) => keys.some((key) => row[key] !== null && row[key] !== undefined));
}

export function normalizeScopeChange(confidence: DeliveryConfidenceDetail) {
  const added = confidence.inputs.scope_added_count;
  const removed = confidence.inputs.scope_removed_count;
  return {
    scope_change_count: confidence.inputs.scope_change_count,
    scope_creep_pct:
      confidence.inputs.scope_stability_index === null
        ? null
        : Number((confidence.inputs.scope_stability_index * 100).toFixed(2)),
    scope_added_count: added,
    scope_removed_count: removed,
    net_scope_change: added - removed,
  };
}

export function normalizeQualityTrend(metrics: SprintMetricValues) {
  return {
    open_high_severity_bugs: metrics.open_high_severity_bugs,
    bugs_created_during_sprint: metrics.bugs_created_during_sprint,
    reopen_rate_pct: metrics.reopen_rate_pct,
  };
}

function scopeCreepStatus(scopeCreepPct: number | null): RiskHeatmapStatus {
  if (scopeCreepPct === null) {
    return "neutral";
  }
  if (scopeCreepPct > scopeCreepStatusThresholds.critical) {
    return "critical";
  }
  if (scopeCreepPct > scopeCreepStatusThresholds.watch) {
    return "watch";
  }
  return "healthy";
}

function effectiveStatus(...statuses: RiskHeatmapStatus[]) {
  return getSprintGroupHealthStatus(statuses);
}

export function getRiskHeatmapCellStatus(group: HeatmapGroup, row: SprintChartHistoryPoint): RiskHeatmapStatus {
  if (group === "Delivery") {
    return row.delivery_status;
  }
  if (group === "Quality") {
    return row.quality_status;
  }
  if (group === "Flow") {
    return row.flow_status;
  }
  return row.risk_status;
}

export function buildRiskHeatmapRows(rows: SprintChartHistoryPoint[]): RiskHeatmapCell[] {
  const groups: HeatmapGroup[] = ["Delivery", "Quality", "Flow", "Risk"];
  return rows.flatMap((row) =>
    groups.map((group) => ({
      sprint_id: row.sprint_id,
      sprint_name: row.name,
      group,
      status: getRiskHeatmapCellStatus(group, row),
    }))
  );
}

function baseChartRow(source: SprintChartSource): SprintChartHistoryPoint | null {
  const { metrics } = source;
  if (!metrics.is_computed) {
    return null;
  }

  const confidence = hasSprintStoryPoints(metrics) ? metrics.delivery_confidence : null;
  const scope = confidence
    ? normalizeScopeChange(confidence)
    : {
        scope_change_count: 0,
        scope_creep_pct: null,
        scope_added_count: 0,
        scope_removed_count: 0,
        net_scope_change: 0,
      };
  const quality = normalizeQualityTrend(metrics.metrics);
  const committed = confidence ? Number(confidence.inputs.committed_effective_points.toFixed(2)) : null;
  const completed = confidence ? Number(confidence.inputs.completed_effective_points.toFixed(2)) : null;
  const reliability = committed !== null && completed !== null ? calculateReliabilityPct(committed, completed) : null;
  const deliveryStatus = effectiveStatus(
    confidence ? getConfidenceStatusLevel(confidence.score) : "neutral",
    metricStatusToHeatmap(getMetricStatus("completed_scope_pct", metrics.metrics.completed_scope_pct)),
    scopeCreepStatus(scope.scope_creep_pct)
  );

  return {
    sprint_id: source.sprint_id,
    name: source.name,
    is_not_closed: source.is_not_closed,
    delivery_confidence: confidence ? Number(confidence.score.toFixed(2)) : null,
    confidence_delta: null,
    progress_alignment: confidence ? Number(confidence.components.progress_alignment.toFixed(2)) : null,
    velocity_fit: confidence ? Number(confidence.components.velocity_fit.toFixed(2)) : null,
    blocker_health: confidence ? Number(confidence.components.blocker_penalty.toFixed(2)) : null,
    scope_stability: confidence ? Number(confidence.components.scope_stability.toFixed(2)) : null,
    committed_story_points: committed,
    completed_story_points: completed,
    reliability_pct: reliability,
    predictability_avg: null,
    ...scope,
    ...quality,
    median_cycle_time_days: metrics.metrics.median_cycle_time_days,
    delivery_status: deliveryStatus,
    quality_status: effectiveStatus(
      metricStatusToHeatmap(getMetricStatus("open_high_severity_bugs", metrics.metrics.open_high_severity_bugs)),
      metricStatusToHeatmap(getMetricStatus("bugs_created_during_sprint", metrics.metrics.bugs_created_during_sprint)),
      metricStatusToHeatmap(getMetricStatus("reopen_rate_pct", metrics.metrics.reopen_rate_pct))
    ),
    flow_status: metricStatusToHeatmap(getMetricStatus("median_cycle_time_days", metrics.metrics.median_cycle_time_days)),
    risk_status: effectiveStatus(
      metricStatusToHeatmap(getMetricStatus("open_blockers", metrics.metrics.open_blockers)),
      metricStatusToHeatmap(getMetricStatus("rollover_count", metrics.metrics.rollover_count))
    ),
  };
}

export function buildSprintChartHistory(sources: SprintChartSource[]): SprintChartHistoryPoint[] {
  const rows = sources.map(baseChartRow).filter((row): row is SprintChartHistoryPoint => row !== null);
  const closedReliabilityValues: number[] = [];

  return rows.map((row, index) => {
    const previousConfidence = index === 0 ? null : rows[index - 1].delivery_confidence;
    return {
      ...row,
      confidence_delta:
        row.delivery_confidence === null || previousConfidence === null
          ? null
          : Number((row.delivery_confidence - previousConfidence).toFixed(2)),
      predictability_avg: (() => {
      if (row.is_not_closed || row.reliability_pct === null) {
        return null;
      }
      closedReliabilityValues.push(row.reliability_pct);
      if (closedReliabilityValues.length < 3) {
        return null;
      }
      const recent = closedReliabilityValues.slice(-3);
      return Number((recent.reduce((sum, value) => sum + value, 0) / recent.length).toFixed(2));
      })(),
    };
  });
}
