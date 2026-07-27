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
export type ComputationStatus = "COMPUTED" | "PARTIAL" | "NOT_COMPUTED";

export type MetricScope = "release" | "sprint";
export type MetricCategory = "delivery" | "quality" | "flow" | "risk" | "snapshot";
export type MetricUnit = "tickets" | "events" | "percent" | "days" | "score" | "gates";
export type MetricFormat = "integer" | "decimal_1" | "decimal_2" | "decimal_4" | "percent_2";
export type MetricSeverity = "watch" | "critical";
export type MetricComparison = "gt" | "gte" | "lt" | "lte";
export type MetricApiLocation = "metric_values" | "response_field" | "chart_only";
export type MetricPartialValuePolicy =
  | "confirmed_minimum"
  | "calculated_from_available_data"
  | "unavailable"
  | "not_supported";

export interface MetricThresholdMetadata {
  severity: MetricSeverity;
  comparison: MetricComparison;
  value: number;
  meaning: string;
}

export interface MetricAvailabilityMetadata {
  dependencies: string[];
  partial_value_policy: MetricPartialValuePolicy;
  supports_not_applicable: boolean;
  evidence_fields: string[];
  minimum_coverage_pct: number | null;
}

export interface MetricDefinitionMetadata {
  key: string;
  scope: MetricScope;
  api_field: string;
  api_location: MetricApiLocation;
  label: string;
  description: string;
  category: MetricCategory;
  unit: MetricUnit;
  formatting: MetricFormat;
  display_order: number;
  thresholds: MetricThresholdMetadata[];
  severity_meaning: string;
  availability: MetricAvailabilityMetadata;
  historical_series: boolean;
  signal_participation: boolean;
  confidence_participation: boolean;
  chart_participation: boolean;
  report_participation: boolean;
  ruleset_version: number;
}

export interface MetricCatalogResponse {
  catalog_version: number;
  ruleset_version: number;
  release: MetricDefinitionMetadata[];
  sprint: MetricDefinitionMetadata[];
}

export interface SprintMetricValues {
  committed_scope: number | null;
  completed_scope_pct: number | null;
  scope_creep_pct: number | null;
  open_blockers: number | null;
  open_high_severity_bugs: number | null;
  bugs_created_during_sprint: number | null;
  in_progress_count: number | null;
  not_started_count: number | null;
  rollover_count: number | null;
  median_cycle_time_days: number | null;
  reopen_rate_pct: number | null;
  workload_concentration_pct: number | null;
  delivery_confidence_score: number | null;
}

export interface MetricIssueKeys {
  open_blockers: string[];
  open_high_severity_bugs: string[];
  completed_tickets?: string[];
  bugs_created_during_sprint?: string[];
  bugs_created_during_sprint_missing_created_at?: string[];
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
  pointed_issue_count: number;
  initial_commitment_count: number | null;
  committed_effective_points: number;
  completed_effective_points: number;
  remaining_effective_points: number;
  completed_scope_pct: number;
  time_elapsed_pct: number | null;
  historical_velocity: number | null;
  baseline_sprint_count: number;
  baseline_sprints: Array<{
    sprint_id: string;
    coverage_pct: number;
    status: DeliveryConfidenceStatus;
    completed_points: number;
  }>;
  velocity_status: DeliveryConfidenceStatus;
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

export interface SprintScopeMovementEvent {
  history_id: number;
  issue_key: string;
  changed_at: string;
  from_value: string | null;
  to_value: string | null;
}

export interface SprintScopeMovementEvidence {
  calculation_status: ComputationStatus;
  scope_creep_pct: number | null;
  window_start: string | null;
  window_end: string | null;
  current_scope_issue_keys: string[];
  project_issue_keys: string[];
  initial_commitment_count: number;
  scope_change_count: number;
  scope_added_count: number;
  scope_removed_count: number;
  net_scope_change: number;
  scope_change_issue_keys: string[];
  scope_added_issue_keys: string[];
  scope_removed_issue_keys: string[];
  scope_addition_events: SprintScopeMovementEvent[];
  scope_removal_events: SprintScopeMovementEvent[];
  incomplete_history_issue_keys: string[];
  sprint_id: string;
  sprint_name: string;
  sprint_changelog_fields: string[];
}

export interface SprintScopeMovementDetail {
  status: ComputationStatus;
  percentage: number | null;
  explanations: string[];
  evidence: SprintScopeMovementEvidence;
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
  dataStatus: "COMPUTED" | "PARTIAL";
  explanations: string[];
}

export interface MetricAvailabilityContext {
  has_tickets: boolean;
  has_story_points: boolean;
  has_completed_tickets: boolean;
  has_release_scope: boolean;
  has_sprint_scope: boolean;
  has_changelog: boolean;
}

export interface MetricAvailabilityItem {
  status: "COMPUTED" | "PARTIAL" | "NOT_COMPUTED" | "NOT_APPLICABLE";
  available: boolean;
  reason: string | null;
  explanations: string[];
  missing_issue_keys: string[];
  depends_on: string[];
}

export interface MetricAvailability {
  context: MetricAvailabilityContext;
  metrics: Record<string, MetricAvailabilityItem>;
}

export type DeliveryConfidenceStatus = "COMPUTED" | "PARTIAL" | "INCONCLUSIVE" | "NOT_COMPUTED";

export interface StoryPointCoverage {
  total_ticket_count: number;
  pointed_ticket_count: number;
  unpointed_ticket_count: number;
  coverage_pct: number;
  unpointed_issue_keys: string[];
}

export type WorkloadDistributionStatus =
  | "COMPUTED"
  | "PARTIAL"
  | "INCONCLUSIVE"
  | "NOT_COMPUTED"
  | "NOT_APPLICABLE";

export type WorkloadRiskBand = "healthy" | "watch" | "critical";

export interface WorkloadAssigneeTotal {
  assignee_key: string;
  assignee: string;
  story_points: number;
  issue_keys: string[];
}

export interface WorkloadDistributionEvidence {
  calculation_status: WorkloadDistributionStatus;
  workload_concentration_pct: number | null;
  current_scope_issue_keys: string[];
  active_issue_keys: string[];
  included_active_issue_keys: string[];
  excluded_active_issue_keys: string[];
  missing_status_issue_keys: string[];
  assignee_identity_fallback_issue_keys: string[];
  assignee_totals: WorkloadAssigneeTotal[];
  total_active_points: number | null;
  top_assignee: WorkloadAssigneeTotal | null;
  risk_band: WorkloadRiskBand | null;
  story_point_coverage: StoryPointCoverage;
}

export interface WorkloadDistributionDetail {
  status: WorkloadDistributionStatus;
  percentage: number | null;
  explanations: string[];
  evidence: WorkloadDistributionEvidence;
}

export interface SprintMetricsResponse {
  sprint_id: string;
  ruleset_version: number | null;
  ruleset_label: string | null;
  calculation_provenance: Record<string, unknown> | null;
  snapshot_at: string | null;
  computation_status: ComputationStatus;
  unavailable_reason: string | null;
  metrics: SprintMetricValues;
  metric_issue_keys: MetricIssueKeys;
  bugs_created_during_sprint_status: ComputationStatus;
  metric_names: string[];
  metric_availability?: MetricAvailability;
  story_point_coverage: StoryPointCoverage;
  delivery_confidence_status: DeliveryConfidenceStatus;
  delivery_confidence_explanations: string[];
  delivery_confidence: DeliveryConfidenceDetail | null;
  scope_movement: SprintScopeMovementDetail | null;
  workload_distribution: WorkloadDistributionDetail | null;
  confidence_breakdown: ConfidenceBreakdown | null;
  biggest_driver: DriverAnalysis | null;
  recommendations: RecommendationAction[];
  is_computed: boolean;
  snapshot_age_hours: number | null;
}

export interface RecomputeSprintMetricsResponse {
  sprint_id: string;
  snapshot_at: string;
  ruleset_version: number;
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
  ruleset_version: number | null;
  ruleset_label: string | null;
  calculation_provenance: Record<string, unknown> | null;
  snapshot_at: string | null;
  computation_status: ComputationStatus;
  unavailable_reason: string | null;
  metrics: MetricValues;
  metric_issue_keys: MetricIssueKeys;
  metric_names: string[];
  metric_availability?: MetricAvailability;
  metric_thresholds: MetricThresholds | null;
  confidence_score: number | null;
  confidence_breakdown: ConfidenceBreakdown | null;
  biggest_driver: DriverAnalysis | null;
  recommendations: RecommendationAction[];
  is_computed: boolean;
  snapshot_age_hours: number | null;
}

export interface ChartPoint {
  snapshot_at: string;
  value: number | null;
  ruleset_version: number;
  version_boundary: boolean;
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
  confidenceDelta: number | null;
  contributors: SnapshotDeltaContributor[];
}

export interface SnapshotComparisonResponse {
  entity_id: string;
  baseline: SnapshotBaseline;
  current_snapshot_at: string | null;
  baseline_snapshot_at: string | null;
  has_baseline: boolean;
  current_ruleset_version: number | null;
  baseline_ruleset_version: number | null;
  unavailable_reason: string | null;
  comparison: SnapshotDeltaComparison;
}

export interface SnapshotChangeHistoryItem {
  date: string;
  ruleset_version: number;
  version_boundary: boolean;
  confidence: number | null;
  delta: number | null;
  primary_driver: string;
  comparison_unavailable_reason: string | null;
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

export interface SignalRiskAgingTicket {
  key: string;
  age_days: number | null;
  issue_age_days: number | null;
  jira_created_at: string | null;
  risk_started_at: string | null;
  risk_start_source_field: string | null;
  risk_start_source_changed_at: string | null;
  history_complete: boolean;
  explanation: string | null;
}

export interface SignalRiskAgingGroup {
  count: number;
  known_count: number;
  unknown_count: number;
  oldest_age_days: number | null;
  average_age_days: number | null;
  tickets?: SignalRiskAgingTicket[];
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
  unavailable_reason: string | null;
  items: SignalLast24HoursItem[];
}

export interface ReleaseOutlook {
  label: "ON TRACK" | "NEEDS ATTENTION" | "AT RISK" | "NOT COMPUTED";
  signal: string | null;
  confidence_score: number | null;
  snapshot_at: string | null;
  release_date: string | null;
  days_remaining: number | null;
  passed_gate_count: number;
  failed_gate_count: number;
  release_gates: SignalGate[];
  confidence_change_24h: number | null;
  confidence_baseline_at: string | null;
  active_conditions: SignalRiskItem[];
  disclaimer: string;
}

export interface ReleaseSignalResponse {
  release_id: string;
  metric_snapshot_id: number | null;
  ruleset_version: number;
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
  release_outlook: ReleaseOutlook;
  thresholds: SignalThresholds | null;
  calculated_at: string | null;
  updated_at: string | null;
}

export interface RecomputeMetricsResponse {
  release_id: string;
  snapshot_at: string;
  ruleset_version: number;
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
  issue_type: string | null;
  status: string | null;
  priority: string | null;
  assignee: string | null;
  story_points: number | null;
  release_id: string | null;
  is_blocker: boolean;
  jira_created_at: string | null;
  jira_updated_at: string | null;
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
  jira_sync_interval_seconds: number;
  jira_field_story_points: string;
  jira_field_severity: string;
  jira_field_release: string;
  jira_field_sprint: string;
  jira_field_blocker: string;
  jira_changelog_fix_version_fields: string;
  jira_changelog_sprint_fields: string;
  jira_done_statuses: string;
  jira_in_progress_statuses: string;
  jira_high_severity_values: string;
  jira_bug_issue_types: string;
  jira_blocker_issue_types: string;
  jira_blocker_severity_values: string;
  jira_blocked_statuses: string;
  is_complete: boolean;
}

export interface JiraConfigurationUpdate {
  jira_base_url: string;
  jira_user_email: string;
  jira_api_token?: string;
  jira_project_key: string;
  jira_sync_enabled: boolean;
  jira_sync_page_size: number;
  jira_sync_changelog_page_size: number;
  jira_sync_interval_seconds: number;
  jira_field_story_points: string;
  jira_field_severity: string;
  jira_field_release: string;
  jira_field_sprint: string;
  jira_field_blocker: string;
  jira_changelog_fix_version_fields: string;
  jira_changelog_sprint_fields: string;
  jira_done_statuses: string;
  jira_in_progress_statuses: string;
  jira_high_severity_values: string;
  jira_bug_issue_types: string;
  jira_blocker_issue_types: string;
  jira_blocker_severity_values: string;
  jira_blocked_statuses: string;
}

export interface JiraConnectionTestResponse {
  ok: boolean;
  message: string;
  account_id: string | null;
  display_name: string | null;
  project_key: string | null;
  project_accessible: boolean;
}

export interface SyncJiraResponse {
  project_key: string;
  sync_mode: "incremental" | "full";
  fallback_reason: string | null;
  cursor_advanced: boolean;
  releases_fetched: number;
  releases_inserted: number;
  releases_updated: number;
  sprints_inserted: number;
  sprints_updated: number;
  issues_fetched: number;
  issues_inserted: number;
  issues_updated: number;
  issues_skipped: number;
  issue_details_skipped_unchanged: number;
  history_fetched: number;
  history_inserted: number;
  history_skipped: number;
  changelogs_skipped_unchanged: number;
}

export interface HealthResponse {
  status: string;
  service: string;
  environment: string;
}
