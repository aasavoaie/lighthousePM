"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
const jiraConfiguration_1 = require("./jiraConfiguration");
function assertEqual(actual, expected, message) {
    if (actual !== expected) {
        throw new Error(`${message}: expected ${String(expected)}, received ${String(actual)}`);
    }
}
const form = {
    jira_base_url: "https://example.atlassian.net",
    jira_user_email: "operator@example.com",
    jira_api_token: "transient-token",
    jira_project_key: "LHPM",
    jira_sync_enabled: true,
    jira_sync_page_size: "50",
    jira_sync_changelog_page_size: "100",
    jira_sync_interval_minutes: "30",
    jira_field_story_points: "customfield_10016",
    jira_field_severity: "priority",
    jira_field_release: "fixVersions",
    jira_field_sprint: "customfield_10020",
    jira_field_blocker: "",
    jira_changelog_fix_version_fields: "fix version,fixversion",
    jira_changelog_sprint_fields: "sprint",
    jira_done_statuses: "done,closed,resolved",
    jira_in_progress_statuses: "in progress",
    jira_high_severity_values: "high,critical",
    jira_bug_issue_types: "bug",
    jira_blocker_issue_types: "blocker,incident",
    jira_blocker_severity_values: "blocker,critical",
    jira_blocked_statuses: "blocked",
};
const browserSave = (0, jiraConfiguration_1.buildJiraConfigurationUpdate)(form, false);
assertEqual("jira_api_token" in browserSave, false, "browser saves omit the Jira token");
assertEqual(browserSave.jira_sync_interval_seconds, 1800, "minutes are converted to seconds");
const connectionTest = (0, jiraConfiguration_1.buildJiraConfigurationUpdate)(form, true);
assertEqual(connectionTest.jira_api_token, "transient-token", "connection tests include a candidate token");
assertEqual(form.jira_api_token, "transient-token", "building a request does not mutate the form");
