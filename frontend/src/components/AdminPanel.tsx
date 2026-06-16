import { useEffect, useState } from "react";

import { apiClient } from "../api/client";
import type { AdminStatusResponse, SyncJiraResponse } from "../api/types";

interface AdminPanelProps {
  onRecomputeAll: () => Promise<void>;
  isRecomputingAll: boolean;
  recomputeMessage: string | null;
  onOperationalDataChanged: () => void;
  onSyncStateChange?: (isSyncing: boolean) => void;
}

interface SyncLogEntry {
  id: number;
  level: "info" | "success" | "error";
  message: string;
  timestamp: string;
}

function formatTimestamp(value: string | null) {
  if (!value) {
    return "Never";
  }
  return new Date(value).toLocaleString();
}

function formatLogTimestamp(value: string) {
  return new Date(value).toLocaleTimeString();
}

export function AdminPanel({
  onRecomputeAll,
  isRecomputingAll,
  recomputeMessage,
  onOperationalDataChanged,
  onSyncStateChange,
}: AdminPanelProps) {
  const [status, setStatus] = useState<AdminStatusResponse | null>(null);
  const [isLoadingStatus, setIsLoadingStatus] = useState(true);
  const [isSyncing, setIsSyncing] = useState(false);
  const [syncMessage, setSyncMessage] = useState<string | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [syncLogs, setSyncLogs] = useState<SyncLogEntry[]>([]);

  function appendSyncLog(level: SyncLogEntry["level"], message: string) {
    setSyncLogs((current) => [
      ...current.slice(-79),
      {
        id: Date.now() + current.length,
        level,
        message,
        timestamp: new Date().toISOString(),
      },
    ]);
  }

  async function loadStatus() {
    setIsLoadingStatus(true);
    setErrorMessage(null);
    try {
      const response = await apiClient.getAdminStatus();
      setStatus(response);
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : "Failed to load admin status.");
    } finally {
      setIsLoadingStatus(false);
    }
  }

  useEffect(() => {
    void loadStatus();
  }, []);

  async function handleSyncJira() {
    if (isSyncing) {
      return;
    }

    setIsSyncing(true);
    onSyncStateChange?.(true);
    setErrorMessage(null);
    setSyncMessage("Syncing Jira...");
    appendSyncLog("info", "Starting Jira sync. Navigation is locked until ingestion finishes.");
    try {
      appendSyncLog("info", "Request sent to the local backend: POST /sync/jira.");
      const result: SyncJiraResponse = await apiClient.syncJira();
      appendSyncLog(
        "success",
        `Fetched ${result.releases_fetched} releases, ${result.issues_fetched} issues, and ${result.history_fetched} changelog entries for ${result.project_key}.`
      );
      appendSyncLog(
        "success",
        `Database changes: releases +${result.releases_inserted}/${result.releases_updated} updated, sprints +${result.sprints_inserted}/${result.sprints_updated} updated, issues +${result.issues_inserted}/${result.issues_updated} updated.`
      );
      appendSyncLog(
        "success",
        `History inserted ${result.history_inserted}; skipped issues ${result.issues_skipped}; skipped history ${result.history_skipped}.`
      );
      setSyncMessage(
        `Sync complete for ${result.project_key}: issues inserted ${result.issues_inserted}, updated ${result.issues_updated}, history inserted ${result.history_inserted}.`
      );
      appendSyncLog("info", "Refreshing admin status and dashboard data.");
      await loadStatus();
      onOperationalDataChanged();
      appendSyncLog("success", "Jira sync finished successfully.");
    } catch (error) {
      const message = error instanceof Error ? error.message : "Failed to sync Jira.";
      setErrorMessage(message);
      setSyncMessage(null);
      appendSyncLog("error", `Jira sync failed: ${message}`);
    } finally {
      setIsSyncing(false);
      onSyncStateChange?.(false);
    }
  }

  async function handleRecomputeAll() {
    setErrorMessage(null);
    await onRecomputeAll();
    await loadStatus();
  }

  return (
    <section className="panel admin-panel">
      <div className="panel-heading">
        <h2>Admin</h2>
      </div>

      {errorMessage ? <p className="error-text">{errorMessage}</p> : null}
      {isLoadingStatus ? <p className="muted">Loading admin status...</p> : null}

      {!isLoadingStatus && status ? (
        <div className="admin-status-grid">
          <p>
            <strong>Environment:</strong> {status.environment}
          </p>
          <p>
            <strong>Last sync success:</strong> {formatTimestamp(status.last_sync_succeeded_at)}
          </p>
          <p>
            <strong>Last sync failure:</strong> {formatTimestamp(status.last_sync_failed_at)}
          </p>
          <p>
            <strong>Last metrics recompute:</strong> {formatTimestamp(status.last_metrics_recompute_at)}
          </p>
          <p>
            <strong>Last signal recompute:</strong> {formatTimestamp(status.last_signal_recompute_at)}
          </p>
          <p>
            <strong>Last failure summary:</strong> {status.last_sync_failure_summary ?? "None"}
          </p>
        </div>
      ) : null}

      <div className="action-row">
        <button
          type="button"
          className="primary-button"
          disabled={isSyncing || isRecomputingAll}
          onClick={() => void handleSyncJira()}
        >
          {isSyncing ? "Syncing..." : "Sync Jira"}
        </button>
        <button
          type="button"
          className="primary-button"
          disabled={isSyncing || isRecomputingAll}
          onClick={() => void handleRecomputeAll()}
        >
          {isRecomputingAll ? "Recomputing..." : "Recompute All Snapshots"}
        </button>
      </div>

      {syncMessage ? <p className="muted action-status">{syncMessage}</p> : null}
      {recomputeMessage ? <p className="muted action-status">{recomputeMessage}</p> : null}

      <section className="sync-terminal" aria-label="Jira sync log">
        <div className="sync-terminal-heading">
          <h3>Sync Log</h3>
          <button type="button" className="secondary-button compact-button" disabled={isSyncing || syncLogs.length === 0} onClick={() => setSyncLogs([])}>
            Clear
          </button>
        </div>
        <div className="sync-terminal-body" role="log" aria-live="polite">
          {syncLogs.length === 0 ? (
            <p className="sync-terminal-empty">No sync activity yet.</p>
          ) : (
            syncLogs.map((entry) => (
              <p key={entry.id} className={`sync-log-line sync-log-${entry.level}`}>
                <span>{formatLogTimestamp(entry.timestamp)}</span>
                <strong>{entry.level.toUpperCase()}</strong>
                <code>{entry.message}</code>
              </p>
            ))
          )}
        </div>
      </section>
    </section>
  );
}
