import type { Release } from "./api/types";
import {
  getSelectedWorkspaceReleaseId,
  getWorkspaceReleases,
  normalizeProjectKey,
  releaseBelongsToProject,
  resolveWorkspaceReleaseId,
} from "./workspaceContext";

function assertEqual<T>(actual: T, expected: T, message: string) {
  if (actual !== expected) {
    throw new Error(`${message}: expected ${String(expected)}, received ${String(actual)}`);
  }
}

function release(releaseId: string, name: string, projectKey: string, createdAt: string): Release {
  return {
    release_id: releaseId,
    name,
    project_key: projectKey,
    description: null,
    status: "unreleased",
    start_date: null,
    release_date: null,
    created_at: createdAt,
    updated_at: createdAt,
  };
}

const releases = [
  release("LHPM-1", "Shared Release", "LHPM", "2026-01-01T00:00:00Z"),
  release("OTHER-1", "Shared Release", "OTHER", "2026-06-01T00:00:00Z"),
  release("lhpm-2", "LHPM Current", "lhpm", "2026-05-01T00:00:00Z"),
];

const workspaceReleases = getWorkspaceReleases(releases, " lhpm ");

assertEqual(normalizeProjectKey(" lhpm "), "LHPM", "project keys are normalized before scoping");
assertEqual(workspaceReleases.length, 2, "workspace releases include only the active project");
assertEqual(workspaceReleases.some((item) => item.release_id === "OTHER-1"), false, "same-name releases from other projects are excluded");
assertEqual(releaseBelongsToProject(releases[2], "LHPM"), true, "project matching is case-insensitive");
assertEqual(releaseBelongsToProject(releases[1], "LHPM"), false, "another project's release is rejected");
assertEqual(getWorkspaceReleases(releases, null).length, 0, "missing project key does not create a global workspace fallback");
assertEqual(getSelectedWorkspaceReleaseId(workspaceReleases, "OTHER-1"), null, "stale cross-project selection is cleared");
assertEqual(getSelectedWorkspaceReleaseId(workspaceReleases, "LHPM-1"), "LHPM-1", "same-project selection is preserved");
assertEqual(
  resolveWorkspaceReleaseId(workspaceReleases, "OTHER-1", new Date("2026-06-16T00:00:00Z")),
  "lhpm-2",
  "stale selection falls back only within the active project"
);
