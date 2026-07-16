"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.getCurrentRelease = getCurrentRelease;
exports.getCurrentReleaseId = getCurrentReleaseId;
exports.resolveSelectedReleaseId = resolveSelectedReleaseId;
const releasedStatuses = new Set(["released", "closed", "done"]);
const notStartedStatuses = new Set(["not started", "notstarted", "planned", "to do", "todo"]);
function normalizeStatus(status) {
    return (status ?? "").trim().toLowerCase().replace(/[-_]+/g, " ");
}
function dateKeyFromDate(value) {
    const year = value.getFullYear();
    const month = String(value.getMonth() + 1).padStart(2, "0");
    const day = String(value.getDate()).padStart(2, "0");
    return `${year}-${month}-${day}`;
}
function dateKeyFromString(value) {
    return value?.slice(0, 10) ?? null;
}
function includesDate(release, dateKey) {
    const startDate = dateKeyFromString(release.start_date);
    const releaseDate = dateKeyFromString(release.release_date);
    return startDate !== null && releaseDate !== null && startDate <= dateKey && dateKey <= releaseDate;
}
function isReleased(release) {
    return releasedStatuses.has(normalizeStatus(release.status));
}
function isNotStarted(release, dateKey) {
    const normalizedStatus = normalizeStatus(release.status);
    const startDate = dateKeyFromString(release.start_date);
    return notStartedStatuses.has(normalizedStatus) || (startDate !== null && startDate > dateKey);
}
function newestFirst(left, right) {
    const rightCreatedAt = Date.parse(right.created_at);
    const leftCreatedAt = Date.parse(left.created_at);
    if (Number.isFinite(rightCreatedAt) && Number.isFinite(leftCreatedAt) && rightCreatedAt !== leftCreatedAt) {
        return rightCreatedAt - leftCreatedAt;
    }
    return right.release_id.localeCompare(left.release_id);
}
function getCurrentRelease(releases, currentDate = new Date()) {
    const dateKey = dateKeyFromDate(currentDate);
    const dateMatchedRelease = releases.filter((release) => includesDate(release, dateKey)).sort(newestFirst)[0];
    if (dateMatchedRelease) {
        return dateMatchedRelease;
    }
    const activeRelease = releases
        .filter((release) => !isReleased(release) && !isNotStarted(release, dateKey))
        .sort(newestFirst)[0];
    if (activeRelease) {
        return activeRelease;
    }
    return [...releases].sort(newestFirst)[0] ?? null;
}
function getCurrentReleaseId(releases, currentDate = new Date()) {
    return getCurrentRelease(releases, currentDate)?.release_id ?? null;
}
function resolveSelectedReleaseId(releases, selectedReleaseId, currentDate = new Date()) {
    if (selectedReleaseId && releases.some((release) => release.release_id === selectedReleaseId)) {
        return selectedReleaseId;
    }
    return getCurrentReleaseId(releases, currentDate);
}
