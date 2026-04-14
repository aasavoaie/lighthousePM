import { useEffect, useState } from "react";

import { apiClient } from "../api/client";
import type { Issue, IssueListResponse } from "../api/types";

const doneStatuses = new Set(["done", "closed", "resolved"]);
const pageSize = 100;

function isDoneStatus(status: string) {
  return doneStatuses.has(status.trim().toLowerCase());
}

type TicketFilterMode = "not_done" | "done_only";

interface IssuesPanelProps {
  releaseId: string | null;
  refreshNonce: number;
  onSelectIssue: (issueKey: string) => void;
}

export function IssuesPanel({ releaseId, refreshNonce, onSelectIssue }: IssuesPanelProps) {
  const [issueList, setIssueList] = useState<IssueListResponse | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [filterMode, setFilterMode] = useState<TicketFilterMode>("not_done");

  useEffect(() => {
    if (!releaseId) {
      setIssueList(null);
      return;
    }

    const currentReleaseId = releaseId;

    let isActive = true;

    async function loadIssues() {
      setIsLoading(true);
      setErrorMessage(null);
      try {
        let allIssues: Issue[] = [];
        let skip = 0;
        let total = 0;

        while (true) {
          const response = await apiClient.getReleaseIssues(currentReleaseId, skip, pageSize);
          total = response.total;
          allIssues = allIssues.concat(response.items);

          if (allIssues.length >= total || response.items.length === 0) {
            break;
          }

          skip += response.limit;
        }

        if (!isActive) {
          return;
        }
        setIssueList({
          items: allIssues,
          skip: 0,
          limit: allIssues.length,
          total,
        });
      } catch (error) {
        if (!isActive) {
          return;
        }
        setErrorMessage(error instanceof Error ? error.message : "Failed to load issues.");
      } finally {
        if (isActive) {
          setIsLoading(false);
        }
      }
    }

    void loadIssues();

    return () => {
      isActive = false;
    };
  }, [releaseId, refreshNonce]);

  const issues: Issue[] = issueList?.items ?? [];
  const visibleIssues =
    filterMode === "done_only"
      ? issues.filter((issue) => isDoneStatus(issue.status))
      : issues.filter((issue) => !isDoneStatus(issue.status));

  if (!releaseId) {
    return (
      <section className="panel">
        <h2>Issues</h2>
        <p className="muted">Select a release to view issues.</p>
      </section>
    );
  }

  return (
    <section className="panel issues-panel">
      <div className="panel-heading">
        <h2>Issues</h2>
        <span className="muted">{issueList ? `Total ${issueList.total}` : ""}</span>
      </div>

      <div className="issues-filter-row" role="radiogroup" aria-label="Issue status filter">
        <button
          type="button"
          className={`filter-chip ${filterMode === "not_done" ? "active" : ""}`}
          onClick={() => setFilterMode("not_done")}
        >
          Not Done
        </button>
        <button
          type="button"
          className={`filter-chip ${filterMode === "done_only" ? "active" : ""}`}
          onClick={() => setFilterMode("done_only")}
        >
          Done Only
        </button>
      </div>

      {isLoading ? <p className="muted">Loading issues...</p> : null}
      {errorMessage ? <p className="error-text">{errorMessage}</p> : null}
      {!isLoading && !errorMessage && visibleIssues.length === 0 ? (
        <p className="muted">
          {filterMode === "done_only"
            ? "No done tickets for this release."
            : "No not-done tickets for this release."}
        </p>
      ) : null}

      {!isLoading && !errorMessage && visibleIssues.length > 0 ? (
        <div className="table-wrapper">
          <table className="issues-table">
            <thead>
              <tr>
                <th>Key</th>
                <th>Summary</th>
                <th>Status</th>
                <th>Type</th>
                <th>Priority</th>
                <th>Assignee</th>
              </tr>
            </thead>
            <tbody>
              {visibleIssues.map((issue) => (
                <tr key={issue.issue_key}>
                  <td>
                    <button
                      type="button"
                      className="link-button"
                      onClick={() => onSelectIssue(issue.issue_key)}
                    >
                      {issue.issue_key}
                    </button>
                  </td>
                  <td>{issue.summary}</td>
                  <td>{issue.status}</td>
                  <td>{issue.issue_type}</td>
                  <td>{issue.priority ?? "N/A"}</td>
                  <td>{issue.assignee ?? "Unassigned"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
    </section>
  );
}
