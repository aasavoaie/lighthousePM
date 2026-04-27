from datetime import datetime

from pydantic import BaseModel


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
    in_progress_count: int | None
    not_started_count: int | None
    rollover_count: int | None
    median_cycle_time_days: float | None
    reopen_rate_pct: float | None


class SprintMetricIssueKeys(BaseModel):
    open_blockers: list[str]
    open_high_severity_bugs: list[str]


class SprintMetricsResponse(BaseModel):
    sprint_id: str
    snapshot_at: datetime | None
    metrics: SprintMetricValues
    metric_issue_keys: SprintMetricIssueKeys
    metric_names: list[str]
    is_computed: bool
    snapshot_age_hours: float | None


class RecomputeSprintMetricsResponse(BaseModel):
    sprint_id: str
    snapshot_at: datetime
    status: str
