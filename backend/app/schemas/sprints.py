from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.confidence import ConfidenceBreakdown


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
    delivery_confidence_score: float | None


class SprintMetricIssueKeys(BaseModel):
    open_blockers: list[str]
    open_high_severity_bugs: list[str]
    bugs_created_during_sprint: list[str]


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
    initial_commitment_count: int | None = None
    committed_effective_points: float = Field(..., description="Total committed story points for the sprint (uses story points or 1 per issue when points are unavailable).")
    completed_effective_points: float = Field(..., description="Sum of effective points for issues marked done in the sprint.")
    remaining_effective_points: float = Field(..., description="Remaining points computed as max(committed_effective_points - completed_effective_points, 0.0).")
    completed_scope_pct: float
    time_elapsed_pct: float | None
    historical_velocity: float | None
    baseline_sprint_count: int = Field(..., description="Number of historical closed sprints used to compute the historical velocity (Baseline). Defaults to last N closed sprints.")
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


class SprintMetricsResponse(BaseModel):
    sprint_id: str
    snapshot_at: datetime | None
    metrics: SprintMetricValues
    metric_issue_keys: SprintMetricIssueKeys
    metric_names: list[str]
    delivery_confidence: DeliveryConfidenceDetail | None
    confidence_breakdown: ConfidenceBreakdown | None
    is_computed: bool
    snapshot_age_hours: float | None


class RecomputeSprintMetricsResponse(BaseModel):
    sprint_id: str
    snapshot_at: datetime
    status: str
