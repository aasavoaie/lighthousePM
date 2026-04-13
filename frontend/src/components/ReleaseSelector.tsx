import type { Release } from "../api/types";

interface ReleaseSelectorProps {
  releases: Release[];
  selectedReleaseId: string | null;
  isLoading: boolean;
  onChange: (releaseId: string) => void;
}

export function ReleaseSelector({
  releases,
  selectedReleaseId,
  isLoading,
  onChange,
}: ReleaseSelectorProps) {
  return (
    <section className="panel selector-panel">
      <div className="panel-heading">
        <h2>Release</h2>
      </div>
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
            {release.name} ({release.release_id})
          </option>
        ))}
      </select>
    </section>
  );
}