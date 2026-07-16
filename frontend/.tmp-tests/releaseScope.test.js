"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
const releaseScope_1 = require("./releaseScope");
function assertEqual(actual, expected, message) {
    if (actual !== expected) {
        throw new Error(`${message}: expected ${String(expected)}, received ${String(actual)}`);
    }
}
function release(releaseId, name, projectKey, createdAt) {
    return {
        release_id: releaseId,
        name,
        project_key: projectKey,
        description: null,
        status: "released",
        start_date: null,
        release_date: null,
        created_at: createdAt,
        updated_at: createdAt,
    };
}
const releases = [
    release("LHPM-1", "Release 2026.06", "LHPM", "2026-06-01T00:00:00Z"),
    release("OTHER-1", "Release 2026.06", "OTHER", "2026-06-02T00:00:00Z"),
    release("lhpm-2", "Release 2026.07", "lhpm", "2026-06-03T00:00:00Z"),
];
const recent = (0, releaseScope_1.getRecentProjectReleases)(releases, "LHPM", 5);
assertEqual(recent.length, 2, "same release names from other projects are excluded");
assertEqual(recent[0].release_id, "LHPM-1", "older scoped release is kept in chronological chart order");
assertEqual(recent[1].release_id, "lhpm-2", "case-insensitive project releases are included");
assertEqual(recent.some((item) => item.release_id === "OTHER-1"), false, "duplicate release name from another project is not selected");
assertEqual((0, releaseScope_1.releaseMatchesProject)(releases[2], "LHPM"), true, "project key matching is case-insensitive");
assertEqual((0, releaseScope_1.getRecentProjectReleases)(releases, null, 5).length, 0, "missing project key does not fall back to global releases");
