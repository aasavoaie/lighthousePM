from datetime import datetime

from pydantic import BaseModel


class AdminStatusResponse(BaseModel):
    service: str
    environment: str
    last_sync_succeeded_at: datetime | None
    last_sync_failed_at: datetime | None
    last_sync_failure_summary: str | None
    last_metrics_recompute_at: datetime | None
    last_signal_recompute_at: datetime | None
