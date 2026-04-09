from datetime import datetime

from pydantic import BaseModel


class MetricValues(BaseModel):
    open_blockers: int | None
    open_high_severity_bugs: int | None
    scope_completed_pct: float | None
    scope_churn_7d_pct: float | None
    median_cycle_time_days: float | None
    reopen_rate_pct: float | None


class ReleaseMetricsResponse(BaseModel):
    release_id: str
    snapshot_at: datetime | None
    metrics: MetricValues


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


class RecomputeMetricsResponse(BaseModel):
    release_id: str
    snapshot_at: datetime
    status: str
