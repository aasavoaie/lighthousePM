"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.normalizeProjectKey = normalizeProjectKey;
exports.releaseBelongsToProject = releaseBelongsToProject;
exports.getWorkspaceReleases = getWorkspaceReleases;
exports.getSelectedWorkspaceReleaseId = getSelectedWorkspaceReleaseId;
exports.resolveWorkspaceReleaseId = resolveWorkspaceReleaseId;
const releaseSelection_1 = require("./releaseSelection");
function normalizeProjectKey(projectKey) {
    const normalized = projectKey?.trim().toUpperCase();
    return normalized ? normalized : null;
}
function releaseBelongsToProject(release, projectKey) {
    const normalizedProjectKey = normalizeProjectKey(projectKey);
    if (!normalizedProjectKey) {
        return false;
    }
    return normalizeProjectKey(release.project_key) === normalizedProjectKey;
}
function getWorkspaceReleases(releases, projectKey) {
    return releases.filter((release) => releaseBelongsToProject(release, projectKey));
}
function getSelectedWorkspaceReleaseId(releases, selectedReleaseId) {
    if (!selectedReleaseId) {
        return null;
    }
    return releases.some((release) => release.release_id === selectedReleaseId) ? selectedReleaseId : null;
}
function resolveWorkspaceReleaseId(releases, selectedReleaseId, currentDate = new Date()) {
    return (0, releaseSelection_1.resolveSelectedReleaseId)(releases, selectedReleaseId, currentDate);
}
