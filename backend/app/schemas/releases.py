from datetime import datetime

from pydantic import BaseModel


class ReleaseResponse(BaseModel):
    release_id: str
    name: str
    project_key: str
    description: str | None
    status: str | None
    start_date: datetime | None
    release_date: datetime | None
    created_at: datetime
    updated_at: datetime


class ReleaseListResponse(BaseModel):
    items: list[ReleaseResponse]
    skip: int
    limit: int
    total: int
