from datetime import datetime

from pydantic import BaseModel


class MetricValues(BaseModel):
    open_blockers: int | None
    open_high_severity_bugs: int | None
    scope_completed_pct: float | None
    scope_churn_7d_pct: float | None
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
    snapshot_at: datetime | None
    metrics: MetricValues
    metric_issue_keys: MetricIssueKeys
    metric_names: list[str]
    metric_thresholds: MetricThresholds | None
    is_computed: bool
    snapshot_age_hours: float | None


class ChartPoint(BaseModel):
    snapshot_at: datetime
    value: int | float | None


class MetricSeries(BaseModel):
    open_blockers: list[ChartPoint]
    open_high_severity_bugs: list[ChartPoint]
    scope_completed_pct: list[ChartPoint]
    scope_churn_7d_pct: list[ChartPoint]
    median_cycle_time_days: list[ChartPoint]
    reopen_rate_pct: list[ChartPoint]


class ReleaseChartsResponse(BaseModel):
    release_id: str
    series: MetricSeries
    metric_names: list[str]
    point_count: int


class RecomputeMetricsResponse(BaseModel):
    release_id: str
    snapshot_at: datetime
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
