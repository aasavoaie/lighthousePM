import { useEffect, useState } from "react";

import { apiClient } from "../api/client";
import type { AdminStatusResponse, SyncJiraResponse } from "../api/types";

interface AdminPanelProps {
  onRecomputeAll: () => Promise<void>;
  isRecomputingAll: boolean;
  recomputeMessage: string | null;
  onOperationalDataChanged: () => void;
}

function formatTimestamp(value: string | null) {
  if (!value) {
    return "Never";
  }
  return new Date(value).toLocaleString();
}

export function AdminPanel({
  onRecomputeAll,
  isRecomputingAll,
  recomputeMessage,
  onOperationalDataChanged,
}: AdminPanelProps) {
  const [status, setStatus] = useState<AdminStatusResponse | null>(null);
  const [isLoadingStatus, setIsLoadingStatus] = useState(true);
  const [isSyncing, setIsSyncing] = useState(false);
  const [syncMessage, setSyncMessage] = useState<string | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

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
    setIsSyncing(true);
    setErrorMessage(null);
    setSyncMessage("Syncing Jira...");
    try {
      const result: SyncJiraResponse = await apiClient.syncJira();
      setSyncMessage(
        `Sync complete for ${result.project_key}: issues inserted ${result.issues_inserted}, updated ${result.issues_updated}, history inserted ${result.history_inserted}.`
      );
      await loadStatus();
      onOperationalDataChanged();
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : "Failed to sync Jira.");
    } finally {
      setIsSyncing(false);
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
    </section>
  );
}
