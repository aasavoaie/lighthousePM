"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
const releaseSelection_1 = require("./releaseSelection");
function assertEqual(actual, expected, message) {
    if (actual !== expected) {
        throw new Error(`${message}: expected ${String(expected)}, received ${String(actual)}`);
    }
}
function release(releaseId, status, createdAt) {
    return {
        release_id: releaseId,
        name: releaseId,
        project_key: "LHPM",
        description: null,
        status,
        start_date: null,
        release_date: null,
        created_at: createdAt,
        updated_at: createdAt,
    };
}
const releases = [
    release("10000", "released", "2026-01-01T00:00:00Z"),
    release("10099", "unreleased", "2026-05-01T00:00:00Z"),
];
assertEqual((0, releaseSelection_1.resolveSelectedReleaseId)(releases, null, new Date("2026-06-15T00:00:00Z")), "10099", "newly synced releases select the current release");
assertEqual((0, releaseSelection_1.resolveSelectedReleaseId)(releases, "10000", new Date("2026-06-15T00:00:00Z")), "10000", "an existing user selection is preserved");
assertEqual((0, releaseSelection_1.resolveSelectedReleaseId)(releases, "missing", new Date("2026-06-15T00:00:00Z")), "10099", "a stale selection falls back to the current release");
assertEqual((0, releaseSelection_1.resolveSelectedReleaseId)([], null), null, "empty release data has no selection");
