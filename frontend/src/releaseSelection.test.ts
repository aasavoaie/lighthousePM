import type { Release } from "./api/types";
import { resolveSelectedReleaseId } from "./releaseSelection";

function assertEqual<T>(actual: T, expected: T, message: string) {
  if (actual !== expected) {
    throw new Error(`${message}: expected ${String(expected)}, received ${String(actual)}`);
  }
}

function release(releaseId: string, status: string, createdAt: string): Release {
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

assertEqual(
  resolveSelectedReleaseId(releases, null, new Date("2026-06-15T00:00:00Z")),
  "10099",
  "newly synced releases select the current release"
);

assertEqual(
  resolveSelectedReleaseId(releases, "10000", new Date("2026-06-15T00:00:00Z")),
  "10000",
  "an existing user selection is preserved"
);

assertEqual(
  resolveSelectedReleaseId(releases, "missing", new Date("2026-06-15T00:00:00Z")),
  "10099",
  "a stale selection falls back to the current release"
);

assertEqual(resolveSelectedReleaseId([], null), null, "empty release data has no selection");
