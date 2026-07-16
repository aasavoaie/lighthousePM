"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.confidenceComponentLabels = exports.confidenceComponentOrder = void 0;
exports.roundPercent = roundPercent;
exports.formatConfidencePercent = formatConfidencePercent;
exports.getConfidenceStatus = getConfidenceStatus;
exports.getComponentStatus = getComponentStatus;
exports.getComponentExplanation = getComponentExplanation;
exports.getConfidenceComponentDetails = getConfidenceComponentDetails;
exports.getBiggestDrag = getBiggestDrag;
exports.calculateExpectedVsActualProgress = calculateExpectedVsActualProgress;
exports.getRiskDrivers = getRiskDrivers;
exports.getDeliveryConfidenceSummary = getDeliveryConfidenceSummary;
exports.confidenceComponentOrder = [
    "progress_alignment",
    "velocity_fit",
    "blocker_penalty",
    "scope_stability",
];
exports.confidenceComponentLabels = {
    progress_alignment: "Progress Alignment",
    velocity_fit: "Velocity Fit",
    blocker_penalty: "Blocker Health",
    scope_stability: "Scope Stability",
};
function roundPercent(value) {
    return Math.round(value);
}
function formatConfidencePercent(value) {
    return `${roundPercent(value)}%`;
}
function getConfidenceStatus(value) {
    if (value >= 80) {
        return { level: "healthy", label: "Healthy" };
    }
    if (value >= 60) {
        return { level: "watch", label: "Watch" };
    }
    if (value >= 40) {
        return { level: "risk", label: "Moderate Risk" };
    }
    return { level: "critical", label: "High Risk" };
}
function getComponentStatus(value) {
    if (value >= 80) {
        return { level: "healthy", label: "Healthy" };
    }
    if (value >= 60) {
        return { level: "watch", label: "Watch" };
    }
    if (value >= 40) {
        return { level: "risk", label: "Risk" };
    }
    return { level: "critical", label: "Critical" };
}
function getComponentExplanation(key, value) {
    if (key === "progress_alignment") {
        if (value >= 80) {
            return "Actual progress is aligned with expected sprint progress.";
        }
        if (value >= 60) {
            return "Actual progress is close to expected sprint progress.";
        }
        return "Actual progress is behind expected sprint progress.";
    }
    if (key === "velocity_fit") {
        if (value >= 80) {
            return "Current pace is supported by historical velocity.";
        }
        if (value >= 60) {
            return "Current pace is near historical velocity.";
        }
        return "Current pace is below historical velocity.";
    }
    if (key === "blocker_penalty") {
        if (value >= 80) {
            return "Blocked work is not materially affecting delivery confidence.";
        }
        if (value >= 60) {
            return "Blocked work needs monitoring.";
        }
        return "Blocked work is reducing delivery confidence.";
    }
    if (value >= 80) {
        return "Sprint scope has remained stable.";
    }
    if (value >= 60) {
        return "Scope changes are manageable.";
    }
    return "Scope changed significantly after sprint start.";
}
function getConfidenceComponentDetails(components) {
    return exports.confidenceComponentOrder.map((key) => {
        const score = components[key];
        return {
            key,
            label: exports.confidenceComponentLabels[key],
            score,
            status: getComponentStatus(score),
            explanation: getComponentExplanation(key, score),
        };
    });
}
function getBiggestDrag(components) {
    const [lowest] = getConfidenceComponentDetails(components).sort((left, right) => left.score - right.score ||
        exports.confidenceComponentOrder.indexOf(left.key) - exports.confidenceComponentOrder.indexOf(right.key));
    return lowest;
}
function calculateExpectedVsActualProgress(inputs) {
    const expectedProgress = inputs.time_elapsed_pct;
    const actualProgress = inputs.committed_effective_points > 0
        ? (inputs.completed_effective_points / inputs.committed_effective_points) * 100
        : null;
    return {
        expectedProgress,
        actualProgress,
        gap: expectedProgress !== null && actualProgress !== null ? actualProgress - expectedProgress : null,
    };
}
function getRiskDrivers(components) {
    const drivers = [];
    if (components.progress_alignment < 60) {
        drivers.push({
            message: "Progress is behind expected sprint pace.",
            severity: components.progress_alignment < 40 ? "critical" : "warning",
        });
    }
    if (components.velocity_fit < 60) {
        drivers.push({
            message: "Current pace is below historical velocity.",
            severity: components.velocity_fit < 40 ? "critical" : "warning",
        });
    }
    if (components.scope_stability < 60) {
        drivers.push({
            message: "Scope changed significantly after sprint start.",
            severity: components.scope_stability < 40 ? "critical" : "warning",
        });
    }
    if (components.blocker_penalty < 60) {
        drivers.push({
            message: "Blocked work is reducing delivery confidence.",
            severity: components.blocker_penalty < 40 ? "critical" : "warning",
        });
    }
    if (drivers.length === 0 && getConfidenceComponentDetails(components).every((detail) => detail.score >= 80)) {
        return [{ message: "No major delivery confidence risks detected.", severity: "positive" }];
    }
    return drivers;
}
function formatComponentList(labels) {
    if (labels.length === 0) {
        return "";
    }
    if (labels.length === 1) {
        return labels[0];
    }
    return `${labels.slice(0, -1).join(", ")} and ${labels[labels.length - 1]}`;
}
function capitalizeFirst(value) {
    return value.length === 0 ? value : `${value[0].toUpperCase()}${value.slice(1)}`;
}
function getPrimarySummarySentence(key, value) {
    if (key === "progress_alignment") {
        return value < 60
            ? "Sprint is behind the expected delivery pace."
            : "Sprint progress is tracking close to the expected delivery pace.";
    }
    if (key === "velocity_fit") {
        return value < 60
            ? "Sprint pace is below the historical delivery baseline."
            : "Sprint pace is tracking close to historical velocity.";
    }
    if (key === "blocker_penalty") {
        return value < 60
            ? "Blocked work is weighing on delivery confidence."
            : "Blocker health is not the main delivery constraint.";
    }
    return value < 60
        ? "Scope movement is weighing on delivery confidence."
        : "Scope stability is not the main delivery constraint.";
}
function getDeliveryConfidenceSummary(components) {
    const details = getConfidenceComponentDetails(components);
    if (details.every((detail) => detail.score >= 80)) {
        return "Delivery confidence is healthy across progress, velocity, blocker health, and scope stability.";
    }
    const sorted = [...details].sort((left, right) => left.score - right.score ||
        exports.confidenceComponentOrder.indexOf(left.key) - exports.confidenceComponentOrder.indexOf(right.key));
    const primary = sorted[0];
    const drivers = sorted
        .filter((detail) => detail.score < 80)
        .slice(0, 2)
        .map((detail) => detail.label.toLowerCase());
    const healthyNotes = details
        .filter((detail) => detail.score >= 80)
        .map((detail) => detail.label.toLowerCase());
    const driverSentence = drivers.length > 0
        ? `The main confidence drivers are ${formatComponentList(drivers)}.`
        : "";
    const healthySentence = healthyNotes.length > 0
        ? ` ${capitalizeFirst(formatComponentList(healthyNotes))} ${healthyNotes.length === 1 ? "remains" : "remain"} positive.`
        : "";
    return `${getPrimarySummarySentence(primary.key, primary.score)} ${driverSentence}${healthySentence}`.trim();
}
