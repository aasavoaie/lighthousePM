from datetime import datetime

from pydantic import BaseModel


class MetricSnapshotResponse(BaseModel):
    release_id: str
    snapshot_at: datetime
    open_blockers: int
    open_high_severity_bugs: int
    scope_completed_pct: float
    scope_churn_7d_pct: float
    median_cycle_time_days: float | None
    reopen_rate_pct: float


class RecomputeMetricsResponse(BaseModel):
    release_id: str
    snapshot_at: datetime
