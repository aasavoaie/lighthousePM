from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.schemas.availability import MetricAvailability
from app.schemas.confidence import ConfidenceBreakdown
from app.schemas.drivers import DriverAnalysis
from app.schemas.recommendations import RecommendationAction

ComputationStatus = Literal["COMPUTED", "PARTIAL", "NOT_COMPUTED"]
DeliveryConfidenceStatus = Literal["COMPUTED", "PARTIAL", "INCONCLUSIVE", "NOT_COMPUTED"]


class SprintResponse(BaseModel):
    sprint_id: str
    name: str
    state: str
    project_key: str
    board_id: str | None
    start_date: datetime | None
    end_date: datetime | None
    complete_date: datetime | None
    goal: str | None
    created_at: datetime
    updated_at: datetime


class SprintListResponse(BaseModel):
    items: list[SprintResponse]
    skip: int
    limit: int
    total: int


class CurrentSprintResponse(BaseModel):
    item: SprintResponse | None


class SprintMetricValues(BaseModel):
    committed_scope: int | None
    completed_scope_pct: float | None
    open_blockers: int | None
    open_high_severity_bugs: int | None
    bugs_created_during_sprint: int | None
    in_progress_count: int | None
    not_started_count: int | None
    rollover_count: int | None
    median_cycle_time_days: float | None
    reopen_rate_pct: float | None
    workload_concentration_pct: float | None = None
    delivery_confidence_score: float | None


class SprintMetricIssueKeys(BaseModel):
    open_blockers: list[str]
    open_high_severity_bugs: list[str]
    bugs_created_during_sprint: list[str]
    bugs_created_during_sprint_missing_created_at: list[str]


class DeliveryConfidenceWeights(BaseModel):
    progress_alignment: float
    velocity_fit: float
    blocker_penalty: float
    scope_stability: float


class DeliveryConfidenceComponents(BaseModel):
    progress_alignment: float
    velocity_fit: float
    blocker_penalty: float
    scope_stability: float


class DeliveryConfidenceInputs(BaseModel):
    committed_issue_count: int
    pointed_issue_count: int = 0
    initial_commitment_count: int | None = None
    committed_effective_points: float = Field(..., description="Total valid story points used for the sprint calculation; unpointed tickets are never imputed.")
    completed_effective_points: float = Field(..., description="Sum of effective points for issues marked done in the sprint.")
    remaining_effective_points: float = Field(..., description="Remaining points computed as max(committed_effective_points - completed_effective_points, 0.0).")
    completed_scope_pct: float
    time_elapsed_pct: float | None
    historical_velocity: float | None
    baseline_sprint_count: int = Field(..., description="Number of historical closed sprints used to compute the historical velocity (Baseline). Defaults to last N closed sprints.")
    baseline_sprints: list[dict[str, str | float]] = Field(default_factory=list)
    velocity_status: DeliveryConfidenceStatus = "NOT_COMPUTED"
    remaining_capacity_points: float | None
    blocked_issue_ratio: float = Field(..., description="Fraction of currently open blocker issues divided by the total number of committed issues. If there are no committed issues, this is 0.0.")
    scope_change_count: int
    scope_added_count: int = 0
    scope_removed_count: int = 0
    scope_stability_index: float | None = None
    scope_change_issue_keys: list[str]
    scope_added_issue_keys: list[str] = Field(default_factory=list)
    scope_removed_issue_keys: list[str] = Field(default_factory=list)


class DeliveryConfidenceDetail(BaseModel):
    score: float
    weights: DeliveryConfidenceWeights
    components: DeliveryConfidenceComponents
    inputs: DeliveryConfidenceInputs


class StoryPointCoverage(BaseModel):
    total_ticket_count: int
    pointed_ticket_count: int
    unpointed_ticket_count: int
    coverage_pct: float
    unpointed_issue_keys: list[str]


WorkloadDistributionStatus = Literal[
    "COMPUTED",
    "PARTIAL",
    "INCONCLUSIVE",
    "NOT_COMPUTED",
    "NOT_APPLICABLE",
]


class WorkloadAssigneeTotal(BaseModel):
    assignee_key: str
    assignee: str
    story_points: float
    issue_keys: list[str]


class WorkloadDistributionEvidence(BaseModel):
    calculation_status: WorkloadDistributionStatus
    workload_concentration_pct: float | None
    current_scope_issue_keys: list[str]
    active_issue_keys: list[str]
    included_active_issue_keys: list[str]
    excluded_active_issue_keys: list[str]
    missing_status_issue_keys: list[str]
    assignee_identity_fallback_issue_keys: list[str]
    assignee_totals: list[WorkloadAssigneeTotal]
    total_active_points: float | None
    top_assignee: WorkloadAssigneeTotal | None
    risk_band: Literal["healthy", "watch", "critical"] | None
    story_point_coverage: StoryPointCoverage


class WorkloadDistributionDetail(BaseModel):
    status: WorkloadDistributionStatus
    percentage: float | None
    explanations: list[str]
    evidence: WorkloadDistributionEvidence


class SprintMetricsResponse(BaseModel):
    sprint_id: str
    ruleset_version: int | None
    ruleset_label: str | None
    calculation_provenance: dict[str, Any] | None
    snapshot_at: datetime | None
    computation_status: ComputationStatus
    unavailable_reason: str | None
    metrics: SprintMetricValues
    metric_issue_keys: SprintMetricIssueKeys
    bugs_created_during_sprint_status: ComputationStatus
    metric_names: list[str]
    metric_availability: MetricAvailability
    story_point_coverage: StoryPointCoverage
    delivery_confidence_status: DeliveryConfidenceStatus
    delivery_confidence_explanations: list[str]
    delivery_confidence: DeliveryConfidenceDetail | None
    workload_distribution: WorkloadDistributionDetail | None = None
    confidence_breakdown: ConfidenceBreakdown | None
    biggest_driver: DriverAnalysis | None
    recommendations: list[RecommendationAction]
    is_computed: bool
    snapshot_age_hours: float | None


class RecomputeSprintMetricsResponse(BaseModel):
    sprint_id: str
    snapshot_at: datetime
    ruleset_version: int
    status: str
