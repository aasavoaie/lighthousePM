import { useState } from "react";

import type { Release } from "../api/types";
import { getCurrentReleaseId } from "../releaseSelection";

interface ReleaseSelectorProps {
  releases: Release[];
  selectedReleaseId: string | null;
  selectedRelease: Release | null;
  isLoading: boolean;
  isRecomputing: boolean;
  onChange: (releaseId: string) => void;
  onRecompute: () => void;
}

function formatDate(value: string | null) {
  if (!value) {
    return "N/A";
  }
  return new Date(value).toLocaleDateString();
}

export function ReleaseSelector({
  releases,
  selectedReleaseId,
  selectedRelease,
  isLoading,
  isRecomputing,
  onChange,
  onRecompute,
}: ReleaseSelectorProps) {
  const currentReleaseId = getCurrentReleaseId(releases);
  const [isHealthStatsExpanded, setIsHealthStatsExpanded] = useState(true);

  return (
    <section className="panel release-controls-panel">
      <div className="panel-heading">
        <h2>Release Health Stats</h2>
        <div className="panel-heading-actions">
          <button
            type="button"
            className="secondary-button compact-button"
            aria-expanded={isHealthStatsExpanded}
            onClick={() => setIsHealthStatsExpanded((current) => !current)}
          >
            {isHealthStatsExpanded ? "Minimize" : "Expand"}
          </button>
        </div>
      </div>
      {isHealthStatsExpanded ? (
        <div className="release-controls-layout">
          <div className="release-control-block">
            <label className="field-label" htmlFor="release-selector">
              Select release
            </label>
            <select
              id="release-selector"
              className="select-input"
              disabled={isLoading || releases.length === 0}
              value={selectedReleaseId ?? ""}
              onChange={(event) => onChange(event.target.value)}
            >
              {releases.length === 0 ? <option value="">No releases available</option> : null}
              {releases.map((release) => (
                <option key={release.release_id} value={release.release_id}>
                  {release.release_id === currentReleaseId
                    ? `Current: ${release.name}`
                    : `${release.name} (${release.release_id})`}
                </option>
              ))}
            </select>
            {selectedRelease ? (
              <div className="release-meta">
                <p>
                  <strong>Project:</strong> {selectedRelease.project_key}
                </p>
                <p>
                  <strong>Status:</strong> {selectedRelease.status ?? "Unknown"}
                </p>
                <p>
                  <strong>Start:</strong> {formatDate(selectedRelease.start_date)}
                </p>
                <p>
                  <strong>Release:</strong> {formatDate(selectedRelease.release_date)}
                </p>
              </div>
            ) : null}
          </div>
          <div className="release-control-block release-recompute-block">
            <button
              type="button"
              className="primary-button"
              disabled={!selectedReleaseId || isRecomputing}
              onClick={onRecompute}
            >
              {isRecomputing ? "Recomputing..." : "Recompute Release"}
            </button>
          </div>
        </div>
      ) : null}
    </section>
  );
}
