import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe } from "jest-axe";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { apiClient } from "../api/client";
import type { JiraConfigurationResponse, JiraConnectionTestResponse } from "../api/types";
import { SettingsPanel } from "./SettingsPanel";

vi.mock("../api/client", () => ({
  apiClient: {
    getJiraConfiguration: vi.fn(),
    testJiraConfiguration: vi.fn(),
    updateJiraConfiguration: vi.fn(),
  },
}));

function configuration(): JiraConfigurationResponse {
  return {
    config_path: "C:/lighthousepm/config.json",
    jira_base_url: "https://example.atlassian.net",
    jira_user_email: "ava@example.com",
    jira_api_token_configured: true,
    jira_project_key: "ALPHA",
    jira_sync_enabled: true,
    jira_sync_page_size: 50,
    jira_sync_changelog_page_size: 50,
    jira_sync_interval_seconds: 3600,
    jira_field_story_points: "customfield_10016",
    jira_field_severity: "Severity",
    jira_field_release: "fixVersions",
    jira_field_sprint: "customfield_10020",
    jira_field_blocker: "Flagged",
    jira_changelog_fix_version_fields: "Fix Version,fixVersions",
    jira_changelog_sprint_fields: "Sprint",
    jira_done_statuses: "Done,Closed",
    jira_in_progress_statuses: "In Progress",
    jira_high_severity_values: "High,Critical",
    jira_bug_issue_types: "Bug",
    jira_blocker_issue_types: "Blocker",
    jira_blocker_severity_values: "Blocker",
    jira_blocked_statuses: "Blocked",
    is_complete: true,
  };
}

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((resolvePromise) => {
    resolve = resolvePromise;
  });
  return { promise, resolve };
}

const getJiraConfiguration = vi.mocked(apiClient.getJiraConfiguration);
const testJiraConfiguration = vi.mocked(apiClient.testJiraConfiguration);

describe("settings form accessibility and state", () => {
  beforeEach(() => {
    vi.resetAllMocks();
    getJiraConfiguration.mockResolvedValue(configuration());
  });

  it("associates its controls with labels and has no automated accessibility violations", async () => {
    const { container } = render(<SettingsPanel />);

    expect(await screen.findByLabelText("Base URL")).toHaveValue("https://example.atlassian.net");
    expect(screen.getByLabelText("Email")).toHaveValue("ava@example.com");
    expect(screen.getByLabelText(/API token/)).toHaveAttribute("type", "password");
    expect(screen.getByLabelText("Project key")).toHaveValue("ALPHA");
    expect(screen.getByLabelText("Enable Jira sync")).toBeChecked();
    expect((await axe(container)).violations).toEqual([]);
  });

  it("disables conflicting actions while testing and announces failure", async () => {
    const connectionTest = deferred<JiraConnectionTestResponse>();
    testJiraConfiguration.mockReturnValue(connectionTest.promise);
    const user = userEvent.setup();
    render(<SettingsPanel />);
    await screen.findByLabelText("Base URL");

    await user.click(screen.getByRole("button", { name: "Test Jira Connection" }));
    expect(screen.getByRole("button", { name: "Testing..." })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Save Settings" })).toBeDisabled();

    connectionTest.resolve({
      ok: false,
      message: "Jira credentials were rejected",
      account_id: null,
      display_name: null,
      project_key: "ALPHA",
      project_accessible: false,
    });
    expect(await screen.findByRole("alert")).toHaveTextContent("Jira credentials were rejected");
    expect(screen.getByRole("button", { name: "Test Jira Connection" })).toBeEnabled();
    expect(screen.getByRole("button", { name: "Save Settings" })).toBeEnabled();
  });

  it("announces configuration load errors", async () => {
    getJiraConfiguration.mockRejectedValue(new Error("Configuration unavailable"));
    render(<SettingsPanel />);

    expect(await screen.findByRole("alert")).toHaveTextContent("Configuration unavailable");
    expect(screen.queryByText("Loading settings...")).not.toBeInTheDocument();
  });
});
