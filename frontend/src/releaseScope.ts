import type { Release } from "./api/types";

function normalizeProjectKey(projectKey: string | null | undefined) {
  const normalized = projectKey?.trim().toUpperCase();
  return normalized ? normalized : null;
}

function releaseSortTime(release: Release) {
  const primaryDate = release.release_date ?? release.created_at;
  const parsed = Date.parse(primaryDate);
  return Number.isFinite(parsed) ? parsed : 0;
}

export function releaseMatchesProject(release: Release, projectKey: string | null | undefined) {
  const normalizedProjectKey = normalizeProjectKey(projectKey);
  if (!normalizedProjectKey) {
    return false;
  }
  return normalizeProjectKey(release.project_key) === normalizedProjectKey;
}

export function getRecentProjectReleases(releases: Release[], projectKey: string | null | undefined, limit: number) {
  return releases
    .filter((release) => releaseMatchesProject(release, projectKey))
    .sort((left, right) => releaseSortTime(right) - releaseSortTime(left))
    .slice(0, limit)
    .reverse();
}
