import type { RecomputeAllMetricsResponse } from "../api/types";

export function formatRecomputeAllMessage(result: RecomputeAllMetricsResponse) {
  if (result.releases_failed > 0) {
    const failedReleaseIds = result.errors.map((error) => error.release_id).join(", ");
    return `Recompute finished: ${result.releases_recomputed}/${result.releases_total} releases succeeded, ${result.releases_failed} failed (${failedReleaseIds}).`;
  }
  return `Recompute complete for ${result.releases_recomputed}/${result.releases_total} releases.`;
}
