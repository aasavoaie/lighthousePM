export interface Release {
  release_id: string;
  name: string;
  project_key: string;
  description: string | null;
  status: string | null;
  start_date: string | null;
  release_date: string | null;
  created_at: string;
  updated_at: string;
}

export interface ReleaseListResponse {
  items: Release[];
  skip: number;
  limit: number;
  total: number;
}

export interface MetricValues {
  open_blockers: number | null;
  open_high_severity_bugs: number | null;
  scope_completed_pct: number | null;
  scope_churn_7d_pct: number | null;
  median_cycle_time_days: number | null;
  reopen_rate_pct: number | null;
}

export interface MetricThresholds {
  open_blockers_red: number;
  open_high_severity_bugs_red: number;
  open_high_severity_bugs_yellow: number;
  scope_churn_7d_pct_red: number;
  scope_churn_7d_pct_yellow: number;
  reopen_rate_pct_red: number;
  reopen_rate_pct_yellow: number;
  median_cycle_time_days_yellow: number;
}

export interface ReleaseMetricsResponse {
  release_id: string;
  snapshot_at: string | null;
  metrics: MetricValues;
  metric_names: string[];
  metric_thresholds: MetricThresholds | null;
  is_computed: boolean;
  snapshot_age_hours: number | null;
}

export interface ChartPoint {
  snapshot_at: string;
  value: number | null;
}

export interface MetricSeries {
  open_blockers: ChartPoint[];
  open_high_severity_bugs: ChartPoint[];
  scope_completed_pct: ChartPoint[];
  scope_churn_7d_pct: ChartPoint[];
  median_cycle_time_days: ChartPoint[];
  reopen_rate_pct: ChartPoint[];
}

export interface ReleaseChartsResponse {
  release_id: string;
  series: MetricSeries;
  metric_names: string[];
  point_count: number;
}

export interface SignalReasonDetail {
  metric_name: string;
  level: string;
  value: number;
  comparison: string;
  threshold: number;
  message: string;
}

export interface SignalThresholds {
  open_blockers_red: number;
  open_high_severity_bugs_red: number;
  open_high_severity_bugs_yellow: number;
  scope_churn_7d_pct_red: number;
  scope_churn_7d_pct_yellow: number;
  reopen_rate_pct_red: number;
  reopen_rate_pct_yellow: number;
  median_cycle_time_days_yellow: number;
}

export interface ReleaseSignalResponse {
  release_id: string;
  signal: string | null;
  reasons: string[];
  reason_details: SignalReasonDetail[];
  thresholds: SignalThresholds;
  updated_at: string | null;
}