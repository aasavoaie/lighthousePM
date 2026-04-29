from datetime import datetime

from pydantic import BaseModel


class IssueResponse(BaseModel):
    issue_key: str
    summary: str
    issue_type: str
    status: str
    priority: str | None
    assignee: str | None
    story_points: float | None
    release_id: str | None
    is_blocker: bool
    created_at: datetime
    updated_at: datetime


class IssueListResponse(BaseModel):
    items: list[IssueResponse]
    skip: int
    limit: int
    total: int
