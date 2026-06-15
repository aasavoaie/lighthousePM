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
    jira_field_story_points: str
    jira_field_severity: str
    jira_field_release: str
    jira_field_sprint: str
    jira_field_blocker: str
    jira_changelog_fix_version_fields: str
    jira_changelog_sprint_fields: str
    is_complete: bool


class JiraConfigurationUpdate(BaseModel):
    jira_base_url: str | None = None
    jira_user_email: str | None = None
    jira_api_token: str | None = None
    jira_project_key: str | None = None
    jira_sync_enabled: bool | None = None
    jira_sync_page_size: int | None = None
    jira_sync_changelog_page_size: int | None = None
    jira_field_story_points: str | None = None
    jira_field_severity: str | None = None
    jira_field_release: str | None = None
    jira_field_sprint: str | None = None
    jira_field_blocker: str | None = None
    jira_changelog_fix_version_fields: str | None = None
    jira_changelog_sprint_fields: str | None = None


class JiraConnectionTestResponse(BaseModel):
    ok: bool
    message: str
    account_id: str | None = None
    display_name: str | None = None
    project_key: str | None = None
    project_accessible: bool = False
