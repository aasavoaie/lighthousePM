import type { RecomputeAllMetricsResponse } from "../api/types";
import { formatRecomputeAllMessage } from "./releaseWorkspaceMessages";

function assertEqual(actual: string, expected: string, message: string) {
  if (actual !== expected) {
    throw new Error(`${message}: expected ${expected}, received ${actual}`);
  }
}

function recomputeResult(overrides: Partial<RecomputeAllMetricsResponse>): RecomputeAllMetricsResponse {
  return {
    releases_total: 3,
    releases_recomputed: 3,
    releases_failed: 0,
    elapsed_seconds: 1,
    errors: [],
    ...overrides,
  };
}

assertEqual(
  formatRecomputeAllMessage(recomputeResult({})),
  "Recompute complete for 3/3 releases.",
  "successful recomputation should report the deterministic completion count"
);

assertEqual(
  formatRecomputeAllMessage(
    recomputeResult({
      releases_recomputed: 1,
      releases_failed: 2,
      errors: [
        { release_id: "REL-2", reason: "failure" },
        { release_id: "REL-3", reason: "failure" },
      ],
    })
  ),
  "Recompute finished: 1/3 releases succeeded, 2 failed (REL-2, REL-3).",
  "partial recomputation should retain ordered failed-release evidence"
);
