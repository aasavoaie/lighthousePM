import { useEffect, useState } from "react";

import { apiClient } from "../api/client";
import type { JiraConfigurationResponse, JiraConfigurationUpdate } from "../api/types";

interface SettingsPanelProps {
  onConfigurationSaved?: (config: JiraConfigurationResponse) => void;
}

interface JiraSettingsForm {
  jira_base_url: string;
  jira_user_email: string;
  jira_api_token: string;
  jira_project_key: string;
  jira_sync_enabled: boolean;
  jira_sync_page_size: string;
  jira_sync_changelog_page_size: string;
  jira_sync_interval_minutes: string;
  jira_field_story_points: string;
  jira_field_severity: string;
  jira_field_release: string;
  jira_field_sprint: string;
  jira_field_blocker: string;
  jira_changelog_fix_version_fields: string;
  jira_changelog_sprint_fields: string;
  jira_done_statuses: string;
  jira_in_progress_statuses: string;
  jira_high_severity_values: string;
  jira_bug_issue_types: string;
  jira_blocker_issue_types: string;
  jira_blocker_severity_values: string;
  jira_blocked_statuses: string;
}

function toForm(config: JiraConfigurationResponse): JiraSettingsForm {
  return {
    jira_base_url: config.jira_base_url,
    jira_user_email: config.jira_user_email,
    jira_api_token: "",
    jira_project_key: config.jira_project_key,
    jira_sync_enabled: config.jira_sync_enabled,
    jira_sync_page_size: String(config.jira_sync_page_size),
    jira_sync_changelog_page_size: String(config.jira_sync_changelog_page_size),
    jira_sync_interval_minutes: String(Math.round(config.jira_sync_interval_seconds / 60)),
    jira_field_story_points: config.jira_field_story_points,
    jira_field_severity: config.jira_field_severity,
    jira_field_release: config.jira_field_release,
    jira_field_sprint: config.jira_field_sprint,
    jira_field_blocker: config.jira_field_blocker,
    jira_changelog_fix_version_fields: config.jira_changelog_fix_version_fields,
    jira_changelog_sprint_fields: config.jira_changelog_sprint_fields,
    jira_done_statuses: config.jira_done_statuses,
    jira_in_progress_statuses: config.jira_in_progress_statuses,
    jira_high_severity_values: config.jira_high_severity_values,
    jira_bug_issue_types: config.jira_bug_issue_types,
    jira_blocker_issue_types: config.jira_blocker_issue_types,
    jira_blocker_severity_values: config.jira_blocker_severity_values,
    jira_blocked_statuses: config.jira_blocked_statuses,
  };
}

function toUpdate(form: JiraSettingsForm): JiraConfigurationUpdate {
  const update: JiraConfigurationUpdate = {
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
  if (form.jira_api_token.trim()) {
    update.jira_api_token = form.jira_api_token;
  }
  return update;
}

function setupItems(config: JiraConfigurationResponse | null) {
  return [
    {
      label: "Connection details",
      isDone: Boolean(config?.jira_base_url && config.jira_user_email),
    },
    {
      label: "API token",
      isDone: Boolean(config?.jira_api_token_configured),
    },
    {
      label: "Project",
      isDone: Boolean(config?.jira_project_key),
    },
    {
      label: "Field mappings",
      isDone: Boolean(config?.jira_field_severity && config.jira_field_release && config.jira_changelog_fix_version_fields),
    },
    {
      label: "Classifications",
      isDone: Boolean(
        config?.jira_done_statuses &&
          config.jira_in_progress_statuses &&
          config.jira_high_severity_values &&
          config.jira_bug_issue_types,
      ),
    },
  ];
}

function formatBytes(bytes: number) {
  if (bytes < 1024) {
    return `${bytes} B`;
  }
  const units = ["KB", "MB", "GB", "TB"];
  let value = bytes / 1024;
  let unitIndex = 0;
  while (value >= 1024 && unitIndex < units.length - 1) {
    value /= 1024;
    unitIndex += 1;
  }
  return `${value.toFixed(value >= 10 ? 1 : 2)} ${units[unitIndex]}`;
}

function syncScheduleLabel(config: JiraConfigurationResponse | null) {
  if (!config?.jira_sync_interval_seconds) {
    return "Manual only";
  }
  const minutes = Math.round(config.jira_sync_interval_seconds / 60);
  return minutes >= 60 && minutes % 60 === 0 ? `Every ${minutes / 60} hour(s)` : `Every ${minutes} minute(s)`;
}

function jiraTestSuccessMessage(response: { display_name: string | null; project_key: string | null; project_accessible: boolean }) {
  const accountLabel = response.display_name ? ` as ${response.display_name}` : "";
  const projectLabel =
    response.project_key && response.project_accessible ? ` Project ${response.project_key} is accessible.` : "";
  return `Jira connection verified successfully${accountLabel}.${projectLabel}`;
}

export function SettingsPanel({ onConfigurationSaved }: SettingsPanelProps) {
  const [config, setConfig] = useState<JiraConfigurationResponse | null>(null);
  const [form, setForm] = useState<JiraSettingsForm | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
  const [isTesting, setIsTesting] = useState(false);
  const [statusMessage, setStatusMessage] = useState<string | null>(null);
  const [testMessage, setTestMessage] = useState<string | null>(null);
  const [testSucceeded, setTestSucceeded] = useState<boolean | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [desktopStorage, setDesktopStorage] = useState<LighthouseDesktopStorageInfo | null>(null);
  const [desktopAction, setDesktopAction] = useState<string | null>(null);
  const [isDesktopActionRunning, setIsDesktopActionRunning] = useState(false);

  async function loadConfiguration() {
    setIsLoading(true);
    setErrorMessage(null);
    try {
      const response = await apiClient.getJiraConfiguration();
      setConfig(response);
      setForm(toForm(response));
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : "Failed to load settings.");
    } finally {
      setIsLoading(false);
    }
  }

  useEffect(() => {
    void loadConfiguration();
  }, []);

  async function loadDesktopStorage() {
    if (!window.lighthouseDesktop?.getStorageInfo) {
      return;
    }
    try {
      setDesktopStorage(await window.lighthouseDesktop.getStorageInfo());
    } catch (error) {
      setDesktopAction(error instanceof Error ? error.message : "Failed to load desktop storage.");
    }
  }

  useEffect(() => {
    void loadDesktopStorage();
  }, []);

  function updateField<K extends keyof JiraSettingsForm>(field: K, value: JiraSettingsForm[K]) {
    setForm((current) => (current ? { ...current, [field]: value } : current));
    setTestMessage(null);
    setTestSucceeded(null);
  }

  async function handleSave() {
    if (!form || isSaving) {
      return;
    }

    setIsSaving(true);
    setStatusMessage(null);
    setErrorMessage(null);
    try {
      const token = form.jira_api_token.trim();
      if (token && window.lighthouseDesktop?.storeJiraToken) {
        await window.lighthouseDesktop.storeJiraToken(token);
      }
      const response = await apiClient.updateJiraConfiguration(toUpdate(form));
      setConfig(response);
      setForm(toForm(response));
      onConfigurationSaved?.(response);
      await loadDesktopStorage();
      setStatusMessage("Settings saved.");
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : "Failed to save settings.");
    } finally {
      setIsSaving(false);
    }
  }

  async function handleTestConnection() {
    if (!form || isTesting) {
      return;
    }

    setIsTesting(true);
    setStatusMessage(null);
    setTestMessage(null);
    setTestSucceeded(null);
    setErrorMessage(null);
    try {
      const response = await apiClient.testJiraConfiguration(toUpdate(form));
      setTestMessage(response.ok ? jiraTestSuccessMessage(response) : response.message || "Jira connection test failed.");
      setTestSucceeded(response.ok);
    } catch (error) {
      setTestMessage(error instanceof Error ? `Jira connection test failed: ${error.message}` : "Jira connection test failed.");
      setTestSucceeded(false);
    } finally {
      setIsTesting(false);
    }
  }

  async function runDesktopAction(action: () => Promise<LighthouseDesktopOperationResult>, fallbackMessage: string) {
    if (isDesktopActionRunning) {
      return;
    }

    setIsDesktopActionRunning(true);
    setDesktopAction(null);
    setErrorMessage(null);
    try {
      const response = await action();
      setDesktopAction(response.message ?? fallbackMessage);
      await loadConfiguration();
      await loadDesktopStorage();
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : fallbackMessage);
    } finally {
      setIsDesktopActionRunning(false);
    }
  }

  return (
    <section className="panel settings-panel">
      <div className="panel-heading">
        <div>
          <h2>Settings</h2>
          {config ? <p className="settings-path">{config.config_path}</p> : null}
        </div>
        <button type="button" className="secondary-button compact-button" disabled={isLoading} onClick={() => void loadConfiguration()}>
          Reload
        </button>
      </div>

      {errorMessage ? <p className="error-text">{errorMessage}</p> : null}
      {statusMessage ? <p className="muted action-status">{statusMessage}</p> : null}
      {testMessage ? (
        <p className={testSucceeded ? "success-text action-status" : "error-text action-status"}>{testMessage}</p>
      ) : null}
      {isLoading ? <p className="muted">Loading settings...</p> : null}

      {form ? (
        <form className="settings-form" onSubmit={(event) => event.preventDefault()}>
          <div className="settings-checklist" aria-label="Setup status">
            {setupItems(config).map((item) => (
              <div key={item.label} className={item.isDone ? "settings-check done" : "settings-check"}>
                <span aria-hidden="true">{item.isDone ? "OK" : "TODO"}</span>
                <strong>{item.label}</strong>
              </div>
            ))}
          </div>

          <fieldset className="settings-fieldset">
            <legend>Jira Connection</legend>
            <label className="settings-field">
              <span>Base URL</span>
              <input
                value={form.jira_base_url}
                onChange={(event) => updateField("jira_base_url", event.target.value)}
                placeholder="https://yourcompany.atlassian.net"
              />
            </label>
            <label className="settings-field">
              <span>Email</span>
              <input value={form.jira_user_email} onChange={(event) => updateField("jira_user_email", event.target.value)} />
            </label>
            <label className="settings-field">
              <span>API token {config?.jira_api_token_configured ? "(configured)" : ""}</span>
              <input
                type="password"
                value={form.jira_api_token}
                onChange={(event) => updateField("jira_api_token", event.target.value)}
                autoComplete="new-password"
              />
            </label>
            <label className="settings-field">
              <span>Project key</span>
              <input value={form.jira_project_key} onChange={(event) => updateField("jira_project_key", event.target.value)} />
            </label>
            <label className="settings-toggle">
              <input
                type="checkbox"
                checked={form.jira_sync_enabled}
                onChange={(event) => updateField("jira_sync_enabled", event.target.checked)}
              />
              <span>Enable Jira sync</span>
            </label>
          </fieldset>

          <fieldset className="settings-fieldset">
            <legend>Sync Limits</legend>
            <label className="settings-field">
              <span>Sync interval minutes</span>
              <input
                type="number"
                min="0"
                value={form.jira_sync_interval_minutes}
                onChange={(event) => updateField("jira_sync_interval_minutes", event.target.value)}
              />
            </label>
            <label className="settings-field">
              <span>Issue page size</span>
              <input
                type="number"
                min="1"
                max="100"
                value={form.jira_sync_page_size}
                onChange={(event) => updateField("jira_sync_page_size", event.target.value)}
              />
            </label>
            <label className="settings-field">
              <span>Changelog page size</span>
              <input
                type="number"
                min="1"
                max="100"
                value={form.jira_sync_changelog_page_size}
                onChange={(event) => updateField("jira_sync_changelog_page_size", event.target.value)}
              />
            </label>
            <div className="settings-field settings-field-wide">
              <span>Current schedule</span>
              <strong>{syncScheduleLabel(config)}</strong>
            </div>
          </fieldset>

          <fieldset className="settings-fieldset">
            <legend>Jira Fields</legend>
            <label className="settings-field">
              <span>Story points</span>
              <input
                value={form.jira_field_story_points}
                onChange={(event) => updateField("jira_field_story_points", event.target.value)}
                placeholder="customfield_10016"
              />
            </label>
            <label className="settings-field">
              <span>Sprint</span>
              <input
                value={form.jira_field_sprint}
                onChange={(event) => updateField("jira_field_sprint", event.target.value)}
                placeholder="customfield_10020"
              />
            </label>
            <label className="settings-field">
              <span>Severity</span>
              <input value={form.jira_field_severity} onChange={(event) => updateField("jira_field_severity", event.target.value)} />
            </label>
            <label className="settings-field">
              <span>Release</span>
              <input value={form.jira_field_release} onChange={(event) => updateField("jira_field_release", event.target.value)} />
            </label>
            <label className="settings-field">
              <span>Blocker</span>
              <input value={form.jira_field_blocker} onChange={(event) => updateField("jira_field_blocker", event.target.value)} />
            </label>
            <label className="settings-field settings-field-wide">
              <span>Fix-version changelog aliases</span>
              <input
                value={form.jira_changelog_fix_version_fields}
                onChange={(event) => updateField("jira_changelog_fix_version_fields", event.target.value)}
              />
            </label>
            <label className="settings-field settings-field-wide">
              <span>Sprint changelog aliases</span>
              <input
                value={form.jira_changelog_sprint_fields}
                onChange={(event) => updateField("jira_changelog_sprint_fields", event.target.value)}
              />
            </label>
          </fieldset>

          <fieldset className="settings-fieldset">
            <legend>Jira Classifications</legend>
            <p className="settings-help settings-field-wide">
              Enter comma-separated Jira values. Matching is case-insensitive.
            </p>
            <label className="settings-field settings-field-wide">
              <span>Done statuses</span>
              <input value={form.jira_done_statuses} onChange={(event) => updateField("jira_done_statuses", event.target.value)} />
            </label>
            <label className="settings-field settings-field-wide">
              <span>In-progress statuses</span>
              <input value={form.jira_in_progress_statuses} onChange={(event) => updateField("jira_in_progress_statuses", event.target.value)} />
            </label>
            <label className="settings-field settings-field-wide">
              <span>High-severity values</span>
              <input value={form.jira_high_severity_values} onChange={(event) => updateField("jira_high_severity_values", event.target.value)} />
            </label>
            <label className="settings-field settings-field-wide">
              <span>Bug issue types</span>
              <input value={form.jira_bug_issue_types} onChange={(event) => updateField("jira_bug_issue_types", event.target.value)} />
            </label>
            <label className="settings-field settings-field-wide">
              <span>Blocker issue types</span>
              <input value={form.jira_blocker_issue_types} onChange={(event) => updateField("jira_blocker_issue_types", event.target.value)} />
            </label>
            <label className="settings-field settings-field-wide">
              <span>Blocker severity values</span>
              <input value={form.jira_blocker_severity_values} onChange={(event) => updateField("jira_blocker_severity_values", event.target.value)} />
            </label>
            <label className="settings-field settings-field-wide">
              <span>Blocked statuses</span>
              <input value={form.jira_blocked_statuses} onChange={(event) => updateField("jira_blocked_statuses", event.target.value)} />
            </label>
          </fieldset>

          <fieldset className="settings-fieldset desktop-settings-fieldset">
            <legend>Desktop Storage</legend>
            {window.lighthouseDesktop?.isElectron ? (
              <>
                <div className="storage-summary settings-field-wide">
                  <div>
                    <span>Total local storage</span>
                    <strong>{desktopStorage ? formatBytes(desktopStorage.usage.totalBytes) : "Loading..."}</strong>
                  </div>
                  <div>
                    <span>Database</span>
                    <strong>{desktopStorage ? formatBytes(desktopStorage.usage.databaseBytes) : "Loading..."}</strong>
                  </div>
                  <div>
                    <span>Logs</span>
                    <strong>{desktopStorage ? formatBytes(desktopStorage.usage.logsBytes) : "Loading..."}</strong>
                  </div>
                  <div>
                    <span>Token</span>
                    <strong>{desktopStorage?.exists.encryptedToken ? "Encrypted" : "Not stored"}</strong>
                  </div>
                </div>
                <div className="settings-field settings-field-wide">
                  <span>Local data folder</span>
                  <strong>{desktopStorage?.paths.userDataDirectory ?? "Loading..."}</strong>
                </div>
                <div className="desktop-action-grid settings-field-wide">
                  <button
                    type="button"
                    className="secondary-button"
                    disabled={isDesktopActionRunning || !window.lighthouseDesktop?.revealDataFolder}
                    onClick={() =>
                      void runDesktopAction(
                        () => window.lighthouseDesktop!.revealDataFolder!(),
                        "Could not open the local data folder."
                      )
                    }
                  >
                    Open Data Folder
                  </button>
                  <button
                    type="button"
                    className="secondary-button"
                    disabled={isDesktopActionRunning || !window.lighthouseDesktop?.backupData}
                    onClick={() =>
                      void runDesktopAction(
                        () => window.lighthouseDesktop!.backupData!(),
                        "Could not create backup."
                      )
                    }
                  >
                    Backup
                  </button>
                  <button
                    type="button"
                    className="secondary-button"
                    disabled={isDesktopActionRunning || !window.lighthouseDesktop?.restoreData}
                    onClick={() => {
                      if (window.confirm("Restore will replace local data and restart the backend. Continue?")) {
                        void runDesktopAction(
                          () => window.lighthouseDesktop!.restoreData!(),
                          "Could not restore backup."
                        );
                      }
                    }}
                  >
                    Restore
                  </button>
                  <button
                    type="button"
                    className="secondary-button danger-button"
                    disabled={isDesktopActionRunning || !window.lighthouseDesktop?.clearData}
                    onClick={() => {
                      if (window.confirm("Clear synced Jira data from this laptop? Settings and token will be kept.")) {
                        void runDesktopAction(
                          () => window.lighthouseDesktop!.clearData!(),
                          "Could not clear local data."
                        );
                      }
                    }}
                  >
                    Clear Data
                  </button>
                  <button
                    type="button"
                    className="secondary-button danger-button"
                    disabled={isDesktopActionRunning || !window.lighthouseDesktop?.factoryReset}
                    onClick={() => {
                      if (window.confirm("Factory reset removes local data, settings, logs, and encrypted token. Continue?")) {
                        void runDesktopAction(
                          () => window.lighthouseDesktop!.factoryReset!(),
                          "Could not factory reset local data."
                        );
                      }
                    }}
                  >
                    Factory Reset
                  </button>
                </div>
                {desktopAction ? <p className="muted action-status settings-field-wide">{desktopAction}</p> : null}
              </>
            ) : (
              <p className="muted settings-field-wide">Desktop storage actions are available in the Electron app.</p>
            )}
          </fieldset>

          <div className="action-row">
            <button type="button" className="secondary-button" disabled={isTesting || isSaving} onClick={() => void handleTestConnection()}>
              {isTesting ? "Testing..." : "Test Jira Connection"}
            </button>
            <button type="button" className="primary-button" disabled={isSaving} onClick={() => void handleSave()}>
              {isSaving ? "Saving..." : "Save Settings"}
            </button>
          </div>
        </form>
      ) : null}
    </section>
  );
}
