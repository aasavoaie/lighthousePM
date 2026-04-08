from pydantic import BaseModel


class SyncJiraResponse(BaseModel):
    project_key: str
    releases_fetched: int
    releases_inserted: int
    releases_updated: int
    issues_fetched: int
    issues_inserted: int
    issues_updated: int
    issues_skipped: int
    history_fetched: int
    history_inserted: int
    history_skipped: int
