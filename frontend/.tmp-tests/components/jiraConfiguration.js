"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.buildJiraConfigurationUpdate = buildJiraConfigurationUpdate;
function buildJiraConfigurationUpdate(form, includeToken) {
    const update = {
        jira_base_url: form.jira_base_url,
        jira_user_email: form.jira_user_email,
        jira_project_key: form.jira_project_key,
        jira_sync_enabled: form.jira_sync_enabled,
        jira_sync_page_size: Number(form.jira_sync_page_size),
        jira_sync_changelog_page_size: Number(form.jira_sync_changelog_page_size),
        jira_sync_interval_seconds: Number(form.jira_sync_interval_minutes) * 60,
        jira_field_story_points: form.jira_field_story_points,
        jira_field_severity: form.jira_field_severity,
        jira_field_release: form.jira_field_release,
        jira_field_sprint: form.jira_field_sprint,
        jira_field_blocker: form.jira_field_blocker,
        jira_changelog_fix_version_fields: form.jira_changelog_fix_version_fields,
        jira_changelog_sprint_fields: form.jira_changelog_sprint_fields,
        jira_done_statuses: form.jira_done_statuses,
        jira_in_progress_statuses: form.jira_in_progress_statuses,
        jira_high_severity_values: form.jira_high_severity_values,
        jira_bug_issue_types: form.jira_bug_issue_types,
        jira_blocker_issue_types: form.jira_blocker_issue_types,
        jira_blocker_severity_values: form.jira_blocker_severity_values,
        jira_blocked_statuses: form.jira_blocked_statuses,
    };
    if (includeToken && form.jira_api_token.trim()) {
        update.jira_api_token = form.jira_api_token;
    }
    return update;
}
