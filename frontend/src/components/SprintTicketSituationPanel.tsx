import type { SprintIssue } from "../api/types";

type SprintTicketSituationPanelProps = {
  isExpanded: boolean;
  selectedSprintId: string | null;
  isLoadingDetails: boolean;
  issues: SprintIssue[];
  onToggle: () => void;
  onSelectIssue: (issueKey: string) => void;
};

export function SprintTicketSituationPanel({
  isExpanded,
  selectedSprintId,
  isLoadingDetails,
  issues,
  onToggle,
  onSelectIssue,
}: SprintTicketSituationPanelProps) {
  return (
    <section className="panel issues-panel">
      <div className="panel-heading">
        <h2>Ticket Situation</h2>
        <div className="panel-heading-actions">
          <span className="muted">{issues.length} shown</span>
          <button
            type="button"
            className="secondary-button compact-button"
            aria-expanded={isExpanded}
            onClick={onToggle}
          >
            {isExpanded ? "Minimize" : "Expand"}
          </button>
        </div>
      </div>
      {isExpanded ? (
        <>
          {!selectedSprintId ? <p className="muted">Select a sprint to view issues.</p> : null}
          {selectedSprintId && !isLoadingDetails && issues.length === 0 ? (
            <p className="muted">No issues linked to this sprint.</p>
          ) : null}
          {issues.length > 0 ? (
            <div className="table-wrapper">
              <table className="issues-table">
                <thead>
                  <tr>
                    <th>Key</th>
                    <th>Summary</th>
                    <th>Status</th>
                    <th>Priority</th>
                    <th>Story points</th>
                    <th>Initial scope</th>
                    <th>Assignee</th>
                  </tr>
                </thead>
                <tbody>
                  {issues.map((issue) => (
                    <tr key={issue.issue_key}>
                      <td>
                        <button type="button" className="link-button" onClick={() => onSelectIssue(issue.issue_key)}>
                          {issue.issue_key}
                        </button>
                      </td>
                      <td>{issue.summary}</td>
                      <td>{issue.status ?? "Unavailable"}</td>
                      <td>{issue.priority ?? "None"}</td>
                      <td>{issue.story_points ?? "None"}</td>
                      <td>{issue.in_initial_scope ? "Yes" : "No"}</td>
                      <td>{issue.assignee ?? "Unassigned"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : null}
        </>
      ) : null}
    </section>
  );
}
