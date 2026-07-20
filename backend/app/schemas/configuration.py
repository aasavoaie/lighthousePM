from pydantic import BaseModel


class JiraConfigurationResponse(BaseModel):
    config_path: str
    jira_base_url: str
    jira_user_email: str
    jira_api_token_configured: bool
    jira_project_key: str
    jira_sync_enabled: bool
    jira_sync_page_size: int
    jira_sync_changelog_page_size: int
    jira_sync_interval_seconds: int
    jira_field_story_points: str
    jira_field_severity: str
    jira_field_release: str
    jira_field_sprint: str
    jira_field_blocker: str
    jira_changelog_fix_version_fields: str
    jira_changelog_sprint_fields: str
    jira_done_statuses: str
    jira_in_progress_statuses: str
    jira_high_severity_values: str
    jira_bug_issue_types: str
    jira_blocker_issue_types: str
    jira_blocker_severity_values: str
    jira_blocked_statuses: str
    is_complete: bool


class JiraConfigurationUpdate(BaseModel):
    jira_base_url: str | None = None
    jira_user_email: str | None = None
    jira_api_token: str | None = None
    jira_project_key: str | None = None
    jira_sync_enabled: bool | None = None
    jira_sync_page_size: int | None = None
    jira_sync_changelog_page_size: int | None = None
    jira_sync_interval_seconds: int | None = None
    jira_field_story_points: str | None = None
    jira_field_severity: str | None = None
    jira_field_release: str | None = None
    jira_field_sprint: str | None = None
    jira_field_blocker: str | None = None
    jira_changelog_fix_version_fields: str | None = None
    jira_changelog_sprint_fields: str | None = None
    jira_done_statuses: str | None = None
    jira_in_progress_statuses: str | None = None
    jira_high_severity_values: str | None = None
    jira_bug_issue_types: str | None = None
    jira_blocker_issue_types: str | None = None
    jira_blocker_severity_values: str | None = None
    jira_blocked_statuses: str | None = None


class JiraConnectionTestResponse(BaseModel):
    ok: bool
    message: str
    account_id: str | None = None
    display_name: str | None = None
    project_key: str | None = None
    project_accessible: bool = False
