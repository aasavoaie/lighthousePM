from datetime import datetime

from pydantic import BaseModel


class SignalReasonDetail(BaseModel):
    metric_name: str
    level: str
    value: int | float
    comparison: str
    threshold: int | float
    message: str


class SignalThresholds(BaseModel):
    open_blockers_red: int
    open_high_severity_bugs_red: int
    open_high_severity_bugs_yellow: int
    scope_churn_7d_pct_red: float
    scope_churn_7d_pct_yellow: float
    reopen_rate_pct_red: float
    reopen_rate_pct_yellow: float
    median_cycle_time_days_yellow: float


class ReleaseSignalResponse(BaseModel):
    release_id: str
    signal: str | None
    reasons: list[str]
    reason_details: list[SignalReasonDetail]
    thresholds: SignalThresholds
    updated_at: datetime | None
