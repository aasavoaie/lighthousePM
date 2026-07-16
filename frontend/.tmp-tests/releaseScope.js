"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.releaseMatchesProject = releaseMatchesProject;
exports.getRecentProjectReleases = getRecentProjectReleases;
function normalizeProjectKey(projectKey) {
    const normalized = projectKey?.trim().toUpperCase();
    return normalized ? normalized : null;
}
function releaseSortTime(release) {
    const primaryDate = release.release_date ?? release.created_at;
    const parsed = Date.parse(primaryDate);
    return Number.isFinite(parsed) ? parsed : 0;
}
function releaseMatchesProject(release, projectKey) {
    const normalizedProjectKey = normalizeProjectKey(projectKey);
    if (!normalizedProjectKey) {
        return false;
    }
    return normalizeProjectKey(release.project_key) === normalizedProjectKey;
}
function getRecentProjectReleases(releases, projectKey, limit) {
    return releases
        .filter((release) => releaseMatchesProject(release, projectKey))
        .sort((left, right) => releaseSortTime(right) - releaseSortTime(left))
        .slice(0, limit)
        .reverse();
}
