import { useEffect, useState } from "react";

import { apiClient } from "../api/client";
import type { Issue } from "../api/types";

interface IssueDetailModalProps {
  issueKey: string | null;
  onClose: () => void;
}

export function IssueDetailModal({ issueKey, onClose }: IssueDetailModalProps) {
  const [issue, setIssue] = useState<Issue | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  useEffect(() => {
    if (!issueKey) {
      setIssue(null);
      setErrorMessage(null);
      return;
    }

    const currentIssueKey = issueKey;

    let isActive = true;

    async function loadIssue() {
      setIsLoading(true);
      setErrorMessage(null);
      try {
        const response = await apiClient.getIssue(currentIssueKey);
        if (!isActive) {
          return;
        }
        setIssue(response);
      } catch (error) {
        if (!isActive) {
          return;
        }
        setIssue(null);
        setErrorMessage(error instanceof Error ? error.message : "Failed to load issue detail.");
      } finally {
        if (isActive) {
          setIsLoading(false);
        }
      }
    }

    void loadIssue();

    return () => {
      isActive = false;
    };
  }, [issueKey]);

  if (!issueKey) {
    return null;
  }

  return (
    <div className="modal-overlay" role="dialog" aria-modal="true" aria-label="Issue details">
      <div className="modal-content">
        <div className="panel-heading">
          <h2>Issue {issueKey}</h2>
          <button type="button" className="secondary-button" onClick={onClose}>
            Close
          </button>
        </div>

        {isLoading ? <p className="muted">Loading issue...</p> : null}
        {errorMessage ? <p className="error-text">{errorMessage}</p> : null}

        {!isLoading && !errorMessage && issue ? (
          <dl className="issue-detail-grid">
            <dt>Summary</dt>
            <dd>{issue.summary}</dd>
            <dt>Type</dt>
            <dd>{issue.issue_type}</dd>
            <dt>Status</dt>
            <dd>{issue.status}</dd>
            <dt>Priority</dt>
            <dd>{issue.priority ?? "N/A"}</dd>
            <dt>Assignee</dt>
            <dd>{issue.assignee ?? "Unassigned"}</dd>
            <dt>Release</dt>
            <dd>{issue.release_id ?? "None"}</dd>
            <dt>Blocker</dt>
            <dd>{issue.is_blocker ? "Yes" : "No"}</dd>
            <dt>Created</dt>
            <dd>{new Date(issue.created_at).toLocaleString()}</dd>
            <dt>Updated</dt>
            <dd>{new Date(issue.updated_at).toLocaleString()}</dd>
          </dl>
        ) : null}
      </div>
    </div>
  );
}
