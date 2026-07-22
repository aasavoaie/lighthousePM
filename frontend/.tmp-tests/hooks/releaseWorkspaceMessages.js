"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.formatRecomputeAllMessage = formatRecomputeAllMessage;
function formatRecomputeAllMessage(result) {
    if (result.releases_failed > 0) {
        const failedReleaseIds = result.errors.map((error) => error.release_id).join(", ");
        return `Recompute finished: ${result.releases_recomputed}/${result.releases_total} releases succeeded, ${result.releases_failed} failed (${failedReleaseIds}).`;
    }
    return `Recompute complete for ${result.releases_recomputed}/${result.releases_total} releases.`;
}
