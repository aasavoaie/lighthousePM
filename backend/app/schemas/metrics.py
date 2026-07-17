from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel

from app.schemas.availability import MetricAvailability
from app.schemas.confidence import ConfidenceBreakdown
from app.schemas.drivers import DriverAnalysis
from app.schemas.recommendations import RecommendationAction

ComputationStatus = Literal["COMPUTED", "PARTIAL", "NOT_COMPUTED"]


class MetricValues(BaseModel):
    open_blockers: int | None
    open_high_severity_bugs: int | None
    scope_completed_pct: float | None
    completed_tickets: int | None
    scope_churn_7d_pct: float | None
    scope_added_7d_count: int | None
    scope_removed_7d_count: int | None
    median_cycle_time_days: float | None
    reopen_rate_pct: float | None


class MetricIssueKeys(BaseModel):
    open_blockers: list[str]
    open_high_severity_bugs: list[str]


class MetricThresholds(BaseModel):
    open_blockers_red: int
    open_high_severity_bugs_red: int
    open_high_severity_bugs_yellow: int
    scope_churn_7d_pct_red: float
    scope_churn_7d_pct_yellow: float
    reopen_rate_pct_red: float
    reopen_rate_pct_yellow: float
    median_cycle_time_days_yellow: float


class ReleaseMetricsResponse(BaseModel):
    release_id: str
    ruleset_version: int | None
    ruleset_label: str | None
    calculation_provenance: dict[str, Any] | None
    snapshot_at: datetime | None
    computation_status: ComputationStatus
    unavailable_reason: str | None
    metrics: MetricValues
    metric_issue_keys: MetricIssueKeys
    metric_names: list[str]
    metric_availability: MetricAvailability
    metric_thresholds: MetricThresholds | None
    confidence_score: float | None
    confidence_breakdown: ConfidenceBreakdown | None
    biggest_driver: DriverAnalysis | None
    recommendations: list[RecommendationAction]
    is_computed: bool
    snapshot_age_hours: float | None


class ChartPoint(BaseModel):
    snapshot_at: datetime
    value: int | float | None
    ruleset_version: int
    version_boundary: bool = False


class MetricSeries(BaseModel):
    open_blockers: list[ChartPoint]
    open_high_severity_bugs: list[ChartPoint]
    scope_completed_pct: list[ChartPoint]
    completed_tickets: list[ChartPoint]
    scope_churn_7d_pct: list[ChartPoint]
    scope_added_7d_count: list[ChartPoint]
    scope_removed_7d_count: list[ChartPoint]
    median_cycle_time_days: list[ChartPoint]
    reopen_rate_pct: list[ChartPoint]
    confidence_score: list[ChartPoint]
    gates_passed_count: list[ChartPoint]
    readiness_pct: list[ChartPoint]


class ReleaseChartsResponse(BaseModel):
    release_id: str
    series: MetricSeries
    metric_names: list[str]
    point_count: int
    release_gates_total: int


class RecomputeMetricsResponse(BaseModel):
    release_id: str
    snapshot_at: datetime
    ruleset_version: int
    status: str


class RecomputeAllError(BaseModel):
    release_id: str
    reason: str


class RecomputeAllMetricsResponse(BaseModel):
    releases_total: int
    releases_recomputed: int
    releases_failed: int
    elapsed_seconds: float
    errors: list[RecomputeAllError]
