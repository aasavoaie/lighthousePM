import type { Sprint } from "../api/types";

export type SprintOption = {
  label: string;
  sprint: Sprint;
};

type SprintHealthPanelProps = {
  isExpanded: boolean;
  options: SprintOption[];
  selectedSprintId: string | null;
  selectedSprint: Sprint | null;
  isLoadingList: boolean;
  isRecomputing: boolean;
  snapshotAgeHours: number | null;
  onToggle: () => void;
  onSelectSprint: (sprintId: string | null) => void;
  onRecompute: () => void;
};

function formatDate(value: string | null) {
  if (!value) {
    return "N/A";
  }
  return new Date(value).toLocaleDateString();
}

export function SprintHealthPanel({
  isExpanded,
  options,
  selectedSprintId,
  selectedSprint,
  isLoadingList,
  isRecomputing,
  snapshotAgeHours,
  onToggle,
  onSelectSprint,
  onRecompute,
}: SprintHealthPanelProps) {
  return (
    <section className="panel sprint-controls-panel">
      <div className="panel-heading">
        <h2>Sprint Health Stats</h2>
        <div className="panel-heading-actions">
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
        <div className="sprint-controls-layout">
          <div className="sprint-control-block">
            <label className="field-label" htmlFor="sprint-selector">
              Select sprint
            </label>
            <select
              id="sprint-selector"
              className="select-input"
              value={selectedSprintId ?? ""}
              disabled={isLoadingList || options.length === 0}
              onChange={(event) => onSelectSprint(event.target.value || null)}
            >
              {options.length === 0 ? <option value="">No sprints available</option> : null}
              {options.map((option) => (
                <option key={option.sprint.sprint_id} value={option.sprint.sprint_id}>
                  {option.label}
                </option>
              ))}
            </select>
            {selectedSprint ? (
              <dl className="release-health-card-grid" aria-label="Selected sprint summary">
                <div>
                  <dt>State</dt>
                  <dd>{selectedSprint.state}</dd>
                </div>
                <div>
                  <dt>Start Date</dt>
                  <dd>{formatDate(selectedSprint.start_date)}</dd>
                </div>
                <div>
                  <dt>End Date</dt>
                  <dd>{formatDate(selectedSprint.end_date)}</dd>
                </div>
                <div>
                  <dt>Completed</dt>
                  <dd>{formatDate(selectedSprint.complete_date)}</dd>
                </div>
              </dl>
            ) : null}
          </div>
          <div className="sprint-control-block sprint-recompute-block">
            <button
              type="button"
              className="primary-button"
              disabled={!selectedSprintId || isRecomputing}
              onClick={onRecompute}
            >
              {isRecomputing ? "Recomputing..." : "Recompute Sprint"}
            </button>
            {snapshotAgeHours !== null ? (
              <p className="muted action-status">Age {snapshotAgeHours.toFixed(1)}h</p>
            ) : null}
          </div>
        </div>
      ) : null}
    </section>
  );
}
