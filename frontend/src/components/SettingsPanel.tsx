import { useEffect, useState } from "react";

import { apiClient } from "../api/client";
import type { JiraConfigurationResponse, JiraConfigurationUpdate } from "../api/types";

interface JiraSettingsForm {
  jira_base_url: string;
  jira_user_email: string;
  jira_api_token: string;
  jira_project_key: string;
  jira_sync_enabled: boolean;
  jira_sync_page_size: string;
  jira_sync_changelog_page_size: string;
  jira_field_story_points: string;
  jira_field_severity: string;
  jira_field_release: string;
  jira_field_sprint: string;
  jira_field_blocker: string;
  jira_changelog_fix_version_fields: string;
  jira_changelog_sprint_fields: string;
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
    jira_field_story_points: config.jira_field_story_points,
    jira_field_severity: config.jira_field_severity,
    jira_field_release: config.jira_field_release,
    jira_field_sprint: config.jira_field_sprint,
    jira_field_blocker: config.jira_field_blocker,
    jira_changelog_fix_version_fields: config.jira_changelog_fix_version_fields,
    jira_changelog_sprint_fields: config.jira_changelog_sprint_fields,
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
    jira_field_story_points: form.jira_field_story_points,
    jira_field_severity: form.jira_field_severity,
    jira_field_release: form.jira_field_release,
    jira_field_sprint: form.jira_field_sprint,
    jira_field_blocker: form.jira_field_blocker,
    jira_changelog_fix_version_fields: form.jira_changelog_fix_version_fields,
    jira_changelog_sprint_fields: form.jira_changelog_sprint_fields,
  };
  if (form.jira_api_token.trim()) {
    update.jira_api_token = form.jira_api_token;
  }
  return update;
}

export function SettingsPanel() {
  const [config, setConfig] = useState<JiraConfigurationResponse | null>(null);
  const [form, setForm] = useState<JiraSettingsForm | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
  const [statusMessage, setStatusMessage] = useState<string | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

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

  function updateField<K extends keyof JiraSettingsForm>(field: K, value: JiraSettingsForm[K]) {
    setForm((current) => (current ? { ...current, [field]: value } : current));
  }

  async function handleSave() {
    if (!form || isSaving) {
      return;
    }

    setIsSaving(true);
    setStatusMessage(null);
    setErrorMessage(null);
    try {
      const response = await apiClient.updateJiraConfiguration(toUpdate(form));
      setConfig(response);
      setForm(toForm(response));
      setStatusMessage("Settings saved.");
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : "Failed to save settings.");
    } finally {
      setIsSaving(false);
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
      {isLoading ? <p className="muted">Loading settings...</p> : null}

      {form ? (
        <form className="settings-form" onSubmit={(event) => event.preventDefault()}>
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

          <div className="action-row">
            <button type="button" className="primary-button" disabled={isSaving} onClick={() => void handleSave()}>
              {isSaving ? "Saving..." : "Save Settings"}
            </button>
          </div>
        </form>
      ) : null}
    </section>
  );
}
