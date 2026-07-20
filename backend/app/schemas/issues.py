from datetime import datetime

from pydantic import BaseModel


class IssueResponse(BaseModel):
    issue_key: str
    summary: str
    issue_type: str | None
    status: str | None
    priority: str | None
    assignee: str | None
    story_points: float | None
    release_id: str | None
    is_blocker: bool
    jira_created_at: datetime | None
    jira_updated_at: datetime | None
    created_at: datetime
    updated_at: datetime


class IssueListResponse(BaseModel):
    items: list[IssueResponse]
    skip: int
    limit: int
    total: int


class SprintIssueResponse(IssueResponse):
    in_initial_scope: bool


class SprintIssueListResponse(BaseModel):
    items: list[SprintIssueResponse]
    skip: int
    limit: int
    total: int
