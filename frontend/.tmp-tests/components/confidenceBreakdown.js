"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.confidenceBreakdownStatusLabels = void 0;
exports.formatConfidenceBreakdownScore = formatConfidenceBreakdownScore;
exports.confidenceBreakdownStatusLabels = {
    good: "Good",
    warning: "Warning",
    critical: "Critical",
};
function formatConfidenceBreakdownScore(score, maxScore) {
    if (maxScore === 100) {
        return `${Math.round(score)}%`;
    }
    return `${Number(score.toFixed(1))}/${Number(maxScore.toFixed(1))}`;
}
