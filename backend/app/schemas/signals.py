from datetime import datetime

from pydantic import BaseModel, Field


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


class SignalGate(BaseModel):
    metric_name: str
    label: str
    passed: bool
    value: int | float | None
    comparison: str
    threshold: int | float


class SignalRiskItem(BaseModel):
    metric_name: str
    level: str
    message: str
    value: int | float | None
    contribution_pct: float


class SignalPrimaryRisk(BaseModel):
    metric_name: str
    label: str
    message: str
    contribution_pct: float


class ReleaseSignalResponse(BaseModel):
    release_id: str
    signal: str | None
    status_label: str | None = None
    confidence_score: float | None = None
    summary: str | None = None
    reasons: list[str]
    reason_details: list[SignalReasonDetail]
    release_gates: list[SignalGate] = Field(default_factory=list)
    critical_risks: list[SignalRiskItem] = Field(default_factory=list)
    warnings: list[SignalRiskItem] = Field(default_factory=list)
    primary_risk: SignalPrimaryRisk | None = None
    thresholds: SignalThresholds
    updated_at: datetime | None
