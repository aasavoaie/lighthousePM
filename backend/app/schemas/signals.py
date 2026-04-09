from datetime import datetime

from pydantic import BaseModel


class ReleaseSignalResponse(BaseModel):
    release_id: str
    signal: str | None
    reasons: list[str]
    updated_at: datetime | None
