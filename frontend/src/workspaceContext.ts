import type { Release } from "./api/types";
import { resolveSelectedReleaseId } from "./releaseSelection";

export function normalizeProjectKey(projectKey: string | null | undefined) {
  const normalized = projectKey?.trim().toUpperCase();
  return normalized ? normalized : null;
}

export function releaseBelongsToProject(release: Release, projectKey: string | null | undefined) {
  const normalizedProjectKey = normalizeProjectKey(projectKey);
  if (!normalizedProjectKey) {
    return false;
  }
  return normalizeProjectKey(release.project_key) === normalizedProjectKey;
}

export function getWorkspaceReleases(releases: Release[], projectKey: string | null | undefined) {
  return releases.filter((release) => releaseBelongsToProject(release, projectKey));
}

export function getSelectedWorkspaceReleaseId(releases: Release[], selectedReleaseId: string | null) {
  if (!selectedReleaseId) {
    return null;
  }
  return releases.some((release) => release.release_id === selectedReleaseId) ? selectedReleaseId : null;
}

export function resolveWorkspaceReleaseId(
  releases: Release[],
  selectedReleaseId: string | null,
  currentDate = new Date()
) {
  return resolveSelectedReleaseId(releases, selectedReleaseId, currentDate);
}
