from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class SyncJiraResponse(BaseModel):
    project_key: str
    sync_mode: Literal["incremental", "full"]
    fallback_reason: str | None
    cursor_advanced: bool
    releases_fetched: int
    releases_inserted: int
    releases_updated: int
    sprints_inserted: int
    sprints_updated: int
    issues_fetched: int
    issues_inserted: int
    issues_updated: int
    issues_skipped: int
    issue_details_skipped_unchanged: int
    history_fetched: int
    history_inserted: int
    history_skipped: int
    changelogs_skipped_unchanged: int


class JiraSyncStatusResponse(BaseModel):
    project_key: str
    current_sync_status: Literal["idle", "running", "succeeded", "failed"]
    last_successful_sync_at: datetime | None
    last_successful_jira_updated_at: datetime | None
    last_failed_sync_at: datetime | None
    last_failure_summary: str | None
    latest_sync_result: dict[str, object] | None
