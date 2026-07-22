"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.NO_STORY_POINTS_REASON = exports.NO_TICKETS_REASON = void 0;
exports.hasComputableReleaseConfidence = hasComputableReleaseConfidence;
exports.getReleaseScoreDisplay = getReleaseScoreDisplay;
exports.getReleaseMetricAvailability = getReleaseMetricAvailability;
exports.getReleaseMetricUnavailableBadge = getReleaseMetricUnavailableBadge;
exports.getReleaseMetricDisplay = getReleaseMetricDisplay;
exports.getReleaseChartEmptyMessage = getReleaseChartEmptyMessage;
exports.NO_TICKETS_REASON = "No tickets are available for this scope.";
exports.NO_STORY_POINTS_REASON = "No tickets in this scope have story points.";
function hasComputableReleaseConfidence(metrics) {
    return metrics?.computation_status !== "NOT_COMPUTED" && metrics?.confidence_score !== null;
}
function getReleaseScoreDisplay(metrics) {
    if (metrics?.computation_status === "NOT_COMPUTED") {
        return {
            value: "Not enough data",
            reason: metrics.unavailable_reason ?? exports.NO_TICKETS_REASON,
            isAvailable: false,
        };
    }
    if (metrics?.computation_status === "PARTIAL" && metrics.confidence_score === null) {
        return {
            value: "Inconclusive",
            reason: metrics.unavailable_reason ?? "Classification inputs are incomplete.",
            isAvailable: false,
        };
    }
    return {
        value: null,
        reason: null,
        isAvailable: true,
    };
}
function getReleaseMetricAvailability(metrics, metricName) {
    return metrics?.metric_availability?.metrics[metricName] ?? null;
}
function getReleaseMetricUnavailableBadge(reason) {
    if (!reason) {
        return null;
    }
    if (reason === exports.NO_STORY_POINTS_REASON) {
        return "No story points";
    }
    if (reason === exports.NO_TICKETS_REASON) {
        return "No tickets";
    }
    return "Unavailable";
}
function getReleaseMetricDisplay(metrics, metricName) {
    const availability = getReleaseMetricAvailability(metrics, metricName);
    const explanations = availability?.explanations ?? [];
    if (availability?.status === "PARTIAL" && availability.available) {
        return {
            value: null,
            badge: "Partial",
            reason: availability.explanations[0] ?? availability.reason,
            explanations,
            isAvailable: true,
        };
    }
    if (availability && !availability.available) {
        return {
            value: "N/A",
            badge: availability.status === "PARTIAL" ? "Partial" : getReleaseMetricUnavailableBadge(availability.reason),
            reason: availability.explanations[0] ?? availability.reason,
            explanations,
            isAvailable: false,
        };
    }
    return {
        value: null,
        badge: null,
        reason: null,
        explanations,
        isAvailable: true,
    };
}
function getReleaseChartEmptyMessage(metrics, charts, metricName, defaultMessage) {
    const points = charts?.series[metricName] ?? [];
    const hasComputablePoints = points.some((point) => point.value !== null);
    if (hasComputablePoints) {
        return defaultMessage;
    }
    if (metrics?.computation_status === "NOT_COMPUTED" || metrics?.computation_status === "PARTIAL") {
        return metrics.unavailable_reason ?? exports.NO_TICKETS_REASON;
    }
    return defaultMessage;
}
