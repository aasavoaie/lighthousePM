import type { Release } from "../api/types";

type ReleaseWorkspaceControlsProps = {
  releases: Release[];
  selectedReleaseId: string | null;
  isLoading: boolean;
  isNavigationLocked: boolean;
  onSelectRelease: (releaseId: string | null) => void;
  onOpenDetails: () => void;
};

export function ReleaseWorkspaceControls({
  releases,
  selectedReleaseId,
  isLoading,
  isNavigationLocked,
  onSelectRelease,
  onOpenDetails,
}: ReleaseWorkspaceControlsProps) {
  return (
    <div className="workspace-release-tools">
      <label className="workspace-release-select">
        <span>Release:</span>
        <select
          disabled={isLoading || releases.length === 0 || isNavigationLocked}
          value={selectedReleaseId ?? ""}
          onChange={(event) => onSelectRelease(event.target.value)}
        >
          {releases.length === 0 ? <option value="">No releases</option> : null}
          {releases.map((release) => (
            <option key={release.release_id} value={release.release_id}>
              {release.name}
            </option>
          ))}
        </select>
      </label>
      <button
        type="button"
        className="details-link-button"
        disabled={isNavigationLocked}
        onClick={onOpenDetails}
      >
        View details
      </button>
    </div>
  );
}
