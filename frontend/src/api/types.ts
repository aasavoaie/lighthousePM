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

export interface Sprint {
  sprint_id: string;
  name: string;
  state: string;
  project_key: string;
  board_id: string | null;
  start_date: string | null;
  end_date: string | null;
  complete_date: string | null;
  goal: string | null;
  created_at: string;
  updated_at: string;
}

export interface SprintListResponse {
  items: Sprint[];
  skip: number;
  limit: number;
  total: number;
}

export interface CurrentSprintResponse {
  item: Sprint | null;
}

export type ReportDepth = "summary" | "full";

export interface SprintMetricValues {
  committed_scope: number | null;
  completed_scope_pct: number | null;
  open_blockers: number | null;
  open_high_severity_bugs: number | null;
  bugs_created_during_sprint: number | null;
  in_progress_count: number | null;
  not_started_count: number | null;
  rollover_count: number | null;
  median_cycle_time_days: number | null;
  reopen_rate_pct: number | null;
  delivery_confidence_score: number | null;
}

export interface MetricIssueKeys {
  open_blockers: string[];
  open_high_severity_bugs: string[];
  bugs_created_during_sprint?: string[];
}

export interface DeliveryConfidenceWeights {
  progress_alignment: number;
  velocity_fit: number;
  blocker_penalty: number;
  scope_stability: number;
}

export interface DeliveryConfidenceComponents {
  progress_alignment: number;
  velocity_fit: number;
  blocker_penalty: number;
  scope_stability: number;
}

export interface DeliveryConfidenceInputs {
  committed_issue_count: number;
  initial_commitment_count: number | null;
  committed_effective_points: number;
  completed_effective_points: number;
  remaining_effective_points: number;
  completed_scope_pct: number;
  time_elapsed_pct: number | null;
  historical_velocity: number | null;
  baseline_sprint_count: number;
  remaining_capacity_points: number | null;
  blocked_issue_ratio: number;
  scope_change_count: number;
  scope_added_count: number;
  scope_removed_count: number;
  scope_stability_index: number | null;
  scope_change_issue_keys: string[];
  scope_added_issue_keys: string[];
  scope_removed_issue_keys: string[];
}

export interface DeliveryConfidenceDetail {
  score: number;
  weights: DeliveryConfidenceWeights;
  components: DeliveryConfidenceComponents;
  inputs: DeliveryConfidenceInputs;
}

export type ConfidenceBreakdownStatus = "good" | "warning" | "critical";

export interface ConfidenceBreakdownComponent {
  id: string;
  name: string;
  score: number;
  maxScore: number;
  status: ConfidenceBreakdownStatus;
  explanation: string;
}

export interface ConfidenceBreakdown {
  totalScore: number;
  components: ConfidenceBreakdownComponent[];
}

export interface DriverAnalysis {
  title: string;
  category: string;
  impact: number;
  contributionPercent: number;
  explanation: string;
  recommendation: string;
}

export type RecommendationEffort = "low" | "medium" | "high";

export interface RecommendationAction {
  title: string;
  description: string;
  priority: number;
  confidenceImpact: number;
  effort: RecommendationEffort;
  category: string;
}

export interface SprintMetricsResponse {
  sprint_id: string;
  snapshot_at: string | null;
  metrics: SprintMetricValues;
  metric_issue_keys: MetricIssueKeys;
  metric_names: string[];
  delivery_confidence: DeliveryConfidenceDetail | null;
  confidence_breakdown: ConfidenceBreakdown | null;
  biggest_driver: DriverAnalysis | null;
  recommendations: RecommendationAction[];
  is_computed: boolean;
  snapshot_age_hours: number | null;
}

export interface RecomputeSprintMetricsResponse {
  sprint_id: string;
  snapshot_at: string;
  status: string;
}

export interface MetricValues {
  open_blockers: number | null;
  open_high_severity_bugs: number | null;
  scope_completed_pct: number | null;
  completed_tickets: number | null;
  scope_churn_7d_pct: number | null;
  scope_added_7d_count: number | null;
  scope_removed_7d_count: number | null;
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
  metric_issue_keys: MetricIssueKeys;
  metric_names: string[];
  metric_thresholds: MetricThresholds | null;
  confidence_breakdown: ConfidenceBreakdown | null;
  biggest_driver: DriverAnalysis | null;
  recommendations: RecommendationAction[];
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
  completed_tickets: ChartPoint[];
  scope_churn_7d_pct: ChartPoint[];
  scope_added_7d_count: ChartPoint[];
  scope_removed_7d_count: ChartPoint[];
  median_cycle_time_days: ChartPoint[];
  reopen_rate_pct: ChartPoint[];
  confidence_score: ChartPoint[];
  gates_passed_count: ChartPoint[];
  readiness_pct: ChartPoint[];
}

export interface ReleaseChartsResponse {
  release_id: string;
  series: MetricSeries;
  metric_names: string[];
  point_count: number;
  release_gates_total: number;
}

export type SnapshotBaseline = "previous" | "24h" | "7d";

export interface SnapshotDeltaContributor {
  metric: string;
  delta: number;
  impact: number;
  direction: "up" | "down";
}

export interface SnapshotDeltaComparison {
  confidenceDelta: number;
  contributors: SnapshotDeltaContributor[];
}

export interface SnapshotComparisonResponse {
  entity_id: string;
  baseline: SnapshotBaseline;
  current_snapshot_at: string | null;
  baseline_snapshot_at: string | null;
  has_baseline: boolean;
  comparison: SnapshotDeltaComparison;
}

export interface SnapshotChangeHistoryItem {
  date: string;
  confidence: number | null;
  delta: number | null;
  primary_driver: string;
}

export interface SnapshotChangeHistoryResponse {
  entity_id: string;
  items: SnapshotChangeHistoryItem[];
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
  confidence_score_red_max: number;
  confidence_score_yellow_min: number;
  confidence_score_yellow_max: number;
  confidence_score_green_min: number;
}

export interface SignalGate {
  metric_name: string;
  label: string;
  passed: boolean;
  value: number | null;
  comparison: string;
  threshold: number;
}

export interface SignalRiskItem {
  metric_name: string;
  level: string;
  message: string;
  value: number | null;
  contribution_pct: number;
}

export interface SignalPrimaryRisk {
  metric_name: string;
  label: string;
  message: string;
  contribution_pct: number;
}

export interface SignalRiskAgingGroup {
  count: number;
  oldest_age_days: number | null;
  average_age_days: number | null;
  tickets?: Array<{ key: string; age_days: number }>;
}

export interface SignalRiskAging {
  blockers: SignalRiskAgingGroup;
  high_severity_bugs: SignalRiskAgingGroup;
  as_of: string | null;
}

export interface SignalLast24HoursItem {
  metric_name: string;
  label: string;
  delta: number | null;
  value_type: string;
  impact: "positive" | "negative" | "neutral" | "unknown";
}

export interface SignalLast24Hours {
  as_of: string | null;
  baseline_at: string | null;
  has_baseline: boolean;
  items: SignalLast24HoursItem[];
}

export interface ReleaseSignalResponse {
  release_id: string;
  signal: string | null;
  status_label: string | null;
  confidence_score: number | null;
  confidence_breakdown: ConfidenceBreakdown | null;
  biggest_driver: DriverAnalysis | null;
  summary: string | null;
  reasons: string[];
  reason_details: SignalReasonDetail[];
  release_gates: SignalGate[];
  critical_risks: SignalRiskItem[];
  warnings: SignalRiskItem[];
  primary_risk: SignalPrimaryRisk | null;
  risk_aging: SignalRiskAging;
  last_24_hours: SignalLast24Hours;
  thresholds: SignalThresholds;
  updated_at: string | null;
}

export interface RecomputeMetricsResponse {
  release_id: string;
  snapshot_at: string;
  status: string;
}

export interface RecomputeAllError {
  release_id: string;
  reason: string;
}

export interface RecomputeAllMetricsResponse {
  releases_total: number;
  releases_recomputed: number;
  releases_failed: number;
  elapsed_seconds: number;
  errors: RecomputeAllError[];
}

export interface Issue {
  issue_key: string;
  summary: string;
  issue_type: string;
  status: string;
  priority: string | null;
  assignee: string | null;
  story_points: number | null;
  release_id: string | null;
  is_blocker: boolean;
  created_at: string;
  updated_at: string;
}

export interface IssueListResponse {
  items: Issue[];
  skip: number;
  limit: number;
  total: number;
}

export interface SprintIssue extends Issue {
  in_initial_scope: boolean;
}

export interface SprintIssueListResponse {
  items: SprintIssue[];
  skip: number;
  limit: number;
  total: number;
}

export interface AdminStatusResponse {
  service: string;
  environment: string;
  last_sync_succeeded_at: string | null;
  last_sync_failed_at: string | null;
  last_sync_failure_summary: string | null;
  last_metrics_recompute_at: string | null;
  last_signal_recompute_at: string | null;
}

export interface JiraConfigurationResponse {
  config_path: string;
  jira_base_url: string;
  jira_user_email: string;
  jira_api_token_configured: boolean;
  jira_project_key: string;
  jira_sync_enabled: boolean;
  jira_sync_page_size: number;
  jira_sync_changelog_page_size: number;
  jira_field_story_points: string;
  jira_field_severity: string;
  jira_field_release: string;
  jira_field_sprint: string;
  jira_field_blocker: string;
  jira_changelog_fix_version_fields: string;
  jira_changelog_sprint_fields: string;
}

export interface JiraConfigurationUpdate {
  jira_base_url: string;
  jira_user_email: string;
  jira_api_token?: string;
  jira_project_key: string;
  jira_sync_enabled: boolean;
  jira_sync_page_size: number;
  jira_sync_changelog_page_size: number;
  jira_field_story_points: string;
  jira_field_severity: string;
  jira_field_release: string;
  jira_field_sprint: string;
  jira_field_blocker: string;
  jira_changelog_fix_version_fields: string;
  jira_changelog_sprint_fields: string;
}

export interface SyncJiraResponse {
  project_key: string;
  releases_fetched: number;
  releases_inserted: number;
  releases_updated: number;
  sprints_inserted: number;
  sprints_updated: number;
  issues_fetched: number;
  issues_inserted: number;
  issues_updated: number;
  issues_skipped: number;
  history_fetched: number;
  history_inserted: number;
  history_skipped: number;
}

export interface HealthResponse {
  status: string;
  service: string;
  environment: string;
}
