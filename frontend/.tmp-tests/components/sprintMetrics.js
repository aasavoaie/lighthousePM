"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.sprintNoChangelogReason = exports.sprintNoStoryPointsReason = exports.sprintNoTicketsReason = void 0;
exports.hasSprintStoryPoints = hasSprintStoryPoints;
exports.getSprintStoryPointUnavailableReason = getSprintStoryPointUnavailableReason;
exports.getSprintMetricAvailabilityReason = getSprintMetricAvailabilityReason;
exports.getSprintMetricUnavailableBadge = getSprintMetricUnavailableBadge;
exports.buildSprintStoryPointUiVisibility = buildSprintStoryPointUiVisibility;
exports.formatPercent = formatPercent;
exports.formatWholePercent = formatWholePercent;
exports.formatPoints = formatPoints;
exports.getMetricStatus = getMetricStatus;
exports.getRatioStatus = getRatioStatus;
exports.calculateDelta = calculateDelta;
exports.formatDelta = formatDelta;
exports.getGroupHealth = getGroupHealth;
exports.getGroupSummary = getGroupSummary;
exports.generateFocusAreas = generateFocusAreas;
exports.buildScopeCreepDisplayModel = buildScopeCreepDisplayModel;
exports.buildVelocityHealthDisplayModel = buildVelocityHealthDisplayModel;
exports.buildPredictabilityDisplayModel = buildPredictabilityDisplayModel;
exports.classifyWorkDistribution = classifyWorkDistribution;
exports.buildWorkDistributionDisplayModel = buildWorkDistributionDisplayModel;
exports.buildSprintWorkStateDisplayModel = buildSprintWorkStateDisplayModel;
exports.sprintNoTicketsReason = "No tickets are available for this scope.";
exports.sprintNoStoryPointsReason = "No tickets in this scope have story points.";
exports.sprintNoChangelogReason = "No Jira changelog history is available for this scope.";
function hasSprintStoryPoints(metrics) {
    return metrics?.metric_availability?.context.has_story_points === true;
}
function getSprintStoryPointUnavailableReason(metrics) {
    const deliveryConfidenceAvailability = metrics?.metric_availability?.metrics.delivery_confidence_score;
    if (deliveryConfidenceAvailability && !deliveryConfidenceAvailability.available && deliveryConfidenceAvailability.reason) {
        return deliveryConfidenceAvailability.reason;
    }
    if (metrics?.unavailable_reason) {
        return metrics.unavailable_reason;
    }
    return exports.sprintNoStoryPointsReason;
}
function getSprintMetricAvailabilityReason(metrics, metricName) {
    const availability = metrics?.metric_availability?.metrics[metricName];
    return availability && !availability.available ? availability.reason : null;
}
function getSprintMetricUnavailableBadge(reason) {
    if (!reason) {
        return null;
    }
    if (reason === exports.sprintNoTicketsReason) {
        return "No tickets";
    }
    if (reason === exports.sprintNoStoryPointsReason) {
        return "No story points";
    }
    if (reason === exports.sprintNoChangelogReason) {
        return "No history";
    }
    return "Unavailable";
}
function buildSprintStoryPointUiVisibility(metrics) {
    const hasStoryPointMetrics = hasSprintStoryPoints(metrics);
    const hasComputedMetrics = metrics?.is_computed === true;
    return {
        hasStoryPointMetrics,
        showStoryPointUnavailableMessage: hasComputedMetrics && !hasStoryPointMetrics,
        showStoryPointChartEmptyState: hasComputedMetrics && !hasStoryPointMetrics,
        showPointValues: hasStoryPointMetrics,
        showRiskDrivers: hasStoryPointMetrics,
        showVelocityHealth: hasStoryPointMetrics,
        showTeamPredictability: hasStoryPointMetrics,
        showDeliveryConfidenceBreakdown: hasStoryPointMetrics,
        showDeliveryConfidenceTrend: hasStoryPointMetrics,
        showCommitmentReliability: hasStoryPointMetrics,
        showTicketCountMetrics: hasComputedMetrics,
    };
}
function formatPercent(value) {
    return `${value.toFixed(2)}%`;
}
function formatWholePercent(value) {
    return `${Math.round(value)}%`;
}
function formatPoints(value) {
    return `${Number(value.toFixed(2))} SP`;
}
function getMetricStatus(metricName, value) {
    if (value === null) {
        return "neutral";
    }
    if (metricName === "open_blockers") {
        return value > 0 ? "critical" : "good";
    }
    if (metricName === "open_high_severity_bugs") {
        if (value > 1) {
            return "critical";
        }
        return value > 0 ? "warning" : "good";
    }
    if (metricName === "bugs_created_during_sprint") {
        return value > 0 ? "warning" : "good";
    }
    if (metricName === "completed_scope_pct") {
        if (value >= 80) {
            return "good";
        }
        return value >= 50 ? "warning" : "critical";
    }
    if (metricName === "rollover_count") {
        return value > 0 ? "critical" : "good";
    }
    if (metricName === "median_cycle_time_days") {
        return value > 7 ? "warning" : "good";
    }
    if (metricName === "reopen_rate_pct") {
        if (value > 15) {
            return "critical";
        }
        return value > 10 ? "warning" : "good";
    }
    return "neutral";
}
function getRatioStatus(value, healthy = 85, watch = 60) {
    if (value === null) {
        return "neutral";
    }
    if (value >= healthy) {
        return "good";
    }
    return value >= watch ? "warning" : "critical";
}
function calculateDelta(current, previous) {
    if (current === null || previous === null) {
        return null;
    }
    return current - previous;
}
function formatDelta(delta, formatter) {
    if (delta === null) {
        return null;
    }
    if (delta === 0) {
        return "Unchanged since last snapshot";
    }
    return `${delta > 0 ? "+" : "-"}${formatter(Math.abs(delta))} since last snapshot`;
}
function getGroupHealth(evaluations, group) {
    const groupItems = evaluations.filter((item) => item.group === group);
    if (groupItems.some((item) => item.status === "critical")) {
        return "critical";
    }
    if (groupItems.some((item) => item.status === "warning")) {
        return "warning";
    }
    if (groupItems.some((item) => item.status === "good")) {
        return "good";
    }
    return "neutral";
}
function getGroupSummary(group, evaluations) {
    const groupItems = evaluations.filter((item) => item.group === group);
    const critical = groupItems.filter((item) => item.status === "critical");
    const warning = groupItems.filter((item) => item.status === "warning");
    if (group === "delivery") {
        if (critical.some((item) => item.key === "completed_scope_pct") && critical.some((item) => item.key === "scope_creep")) {
            return "Delivery is at risk due to low completion and high scope creep.";
        }
        if (critical.length > 0 || warning.length > 0) {
            return `Delivery needs attention: ${[...critical, ...warning].map((item) => item.label.toLowerCase()).join(", ")}.`;
        }
        return "Delivery metrics are tracking within expected ranges.";
    }
    if (group === "quality") {
        const highSeverity = [...critical, ...warning].find((item) => item.key === "open_high_severity_bugs");
        if (highSeverity) {
            return "Quality is stable, but high-severity bugs require attention.";
        }
        if (critical.length > 0 || warning.length > 0) {
            return `Quality needs attention: ${[...critical, ...warning].map((item) => item.label.toLowerCase()).join(", ")}.`;
        }
        return "Quality metrics are stable.";
    }
    if (group === "flow") {
        if (critical.length > 0 || warning.length > 0) {
            return `Flow needs attention: ${[...critical, ...warning].map((item) => item.label.toLowerCase()).join(", ")}.`;
        }
        return "Flow metrics are stable.";
    }
    if (group === "risk") {
        if (critical.length > 0 || warning.length > 0) {
            return `Risk needs attention: ${[...critical, ...warning].map((item) => item.label.toLowerCase()).join(", ")}.`;
        }
        return "No major sprint risk indicators are active.";
    }
    return "Sprint work state is summarized from the current sprint snapshot.";
}
function generateFocusAreas(evaluations) {
    const actionable = evaluations
        .map((item, index) => ({ item, index }))
        .filter(({ item }) => item.status === "critical" || item.status === "warning")
        .sort((left, right) => {
        const severityScore = (status) => (status === "critical" ? 0 : 1);
        return severityScore(left.item.status) - severityScore(right.item.status) || left.index - right.index;
    });
    if (actionable.length === 0) {
        return ["No major metric risks detected."];
    }
    return actionable.slice(0, 3).map(({ item }) => item.focusMessage);
}
function buildScopeCreepDisplayModel(confidence) {
    const index = confidence.inputs.scope_stability_index;
    const creepPct = index === null ? null : Number((index * 100).toFixed(2));
    const status = creepPct === null ? "neutral" : creepPct > 20 ? "critical" : creepPct > 10 ? "warning" : "good";
    const added = confidence.inputs.scope_added_count;
    const removed = confidence.inputs.scope_removed_count;
    const netChange = added - removed;
    const issueKeys = confidence.inputs.scope_change_issue_keys ?? [];
    return {
        value: creepPct === null ? "N/A" : formatPercent(creepPct),
        status,
        comparison: confidence.inputs.scope_change_count === 0
            ? "No scope changes after sprint start"
            : `${confidence.inputs.scope_change_count} scope changes after sprint start`,
        impact: confidence.inputs.scope_change_count === 0 ? "positive" : "negative",
        details: [
            `${added} added`,
            `${removed} removed`,
            `Net ${netChange >= 0 ? "+" : ""}${netChange}`,
        ],
        issueKeys: issueKeys.slice(0, 5),
        hiddenIssueCount: Math.max(0, issueKeys.length - 5),
    };
}
function buildVelocityHealthDisplayModel(confidence) {
    const completed = confidence.inputs.completed_effective_points;
    const average = confidence.inputs.historical_velocity;
    const remainingCapacity = confidence.inputs.remaining_capacity_points;
    const projected = remainingCapacity === null ? completed : completed + Math.max(remainingCapacity, 0);
    const pct = average && average > 0 ? Number(((completed / average) * 100).toFixed(0)) : null;
    const status = getRatioStatus(pct, 85, 60);
    if (average === null || average === 0) {
        return {
            value: "Not enough data yet",
            status: "neutral",
            comparison: "Requires closed sprint velocity history.",
            impact: "unknown",
            details: [`Projected completion: ${formatPoints(projected)}`],
        };
    }
    return {
        value: pct === null ? "N/A" : `${pct}%`,
        status,
        comparison: `Velocity health: ${pct}%`,
        impact: status === "good" ? "positive" : "negative",
        details: [
            `Projected completion: ${formatPoints(projected)}`,
            `Historical average: ${formatPoints(average)}`,
        ],
    };
}
function buildPredictabilityDisplayModel(rows) {
    const closedRows = rows.filter((row) => !row.is_not_closed && row.committed_story_points > 0);
    if (closedRows.length < 2) {
        return {
            value: "Not enough data yet",
            status: "neutral",
            comparison: "Requires at least 2 closed sprints.",
            impact: "unknown",
            details: [],
        };
    }
    const ratios = closedRows.map((row) => row.completed_story_points / row.committed_story_points);
    const pct = Number(((ratios.reduce((sum, value) => sum + value, 0) / ratios.length) * 100).toFixed(0));
    const status = getRatioStatus(pct, 90, 75);
    return {
        value: `${pct}%`,
        status,
        comparison: `Last ${closedRows.length} sprints: completed vs committed`,
        impact: status === "good" ? "positive" : status === "warning" ? "neutral" : "negative",
        details: closedRows.map((row) => `${row.name}: ${Number(row.completed_story_points.toFixed(2))}/${Number(row.committed_story_points.toFixed(2))} SP`),
    };
}
function issueStoryPoints(issue) {
    return issue.story_points !== null && issue.story_points !== undefined && issue.story_points >= 0 ? issue.story_points : null;
}
function isDoneStatus(status) {
    const normalized = status.trim().toLowerCase();
    return normalized === "done" || normalized === "closed" || normalized === "resolved";
}
function classifyWorkDistribution(topAssigneePct) {
    if (topAssigneePct === null) {
        return "neutral";
    }
    if (topAssigneePct > 50) {
        return "critical";
    }
    return topAssigneePct >= 35 ? "warning" : "good";
}
function buildWorkDistributionDisplayModel(issues) {
    const activeIssues = issues.filter((issue) => !isDoneStatus(issue.status));
    if (activeIssues.length === 0) {
        return {
            title: "Workload concentration",
            value: "Not enough data yet",
            status: "neutral",
            comparison: "Requires active sprint work.",
            impact: "unknown",
            details: [],
        };
    }
    const pointedActiveIssues = activeIssues
        .map((issue) => ({ issue, storyPoints: issueStoryPoints(issue) }))
        .filter((entry) => entry.storyPoints !== null);
    const unpointedCount = activeIssues.length - pointedActiveIssues.length;
    if (pointedActiveIssues.length === 0) {
        return {
            title: "Workload concentration",
            value: "Unavailable",
            status: "neutral",
            comparison: "Requires story points on active sprint work.",
            impact: "unknown",
            details: ["No active sprint tickets have story points."],
        };
    }
    const totals = new Map();
    for (const { issue, storyPoints } of pointedActiveIssues) {
        const assignee = issue.assignee?.trim() || "Unassigned";
        totals.set(assignee, (totals.get(assignee) ?? 0) + storyPoints);
    }
    const totalPoints = Array.from(totals.values()).reduce((sum, value) => sum + value, 0);
    if (totalPoints === 0) {
        return {
            title: "Workload concentration",
            value: "Unavailable",
            status: "neutral",
            comparison: "Requires positive story-point values.",
            impact: "unknown",
            details: unpointedCount > 0
                ? [`${unpointedCount} active ticket${unpointedCount === 1 ? "" : "s"} excluded because story points are missing.`]
                : ["Active sprint tickets have 0 total story points."],
        };
    }
    const rows = Array.from(totals.entries())
        .map(([assignee, points]) => ({
        assignee,
        pct: Number(((points / totalPoints) * 100).toFixed(0)),
    }))
        .sort((left, right) => right.pct - left.pct || left.assignee.localeCompare(right.assignee));
    const top = rows[0];
    const status = classifyWorkDistribution(top.pct);
    return {
        title: "Workload concentration",
        value: `${top.pct}%`,
        status,
        comparison: `Top assignee: ${top.assignee}`,
        impact: status === "good" ? "positive" : "negative",
        details: [
            ...(unpointedCount > 0
                ? [`${unpointedCount} active ticket${unpointedCount === 1 ? "" : "s"} excluded because story points are missing.`]
                : []),
            `${top.pct}% of pointed active work`,
            "Top 3 assignees",
            ...rows.slice(0, 3).map((row) => `${row.assignee}: ${row.pct}%`),
        ],
    };
}
function buildSprintWorkStateDisplayModel(metrics, issues) {
    const committed = metrics.committed_scope;
    const inProgress = metrics.in_progress_count;
    const notStarted = metrics.not_started_count;
    const rollover = metrics.rollover_count;
    const doneCount = issues.filter((issue) => isDoneStatus(issue.status)).length;
    const blocked = metrics.open_blockers;
    const status = blocked !== null && blocked > 0 ? "critical" : rollover !== null && rollover > 0 ? "warning" : "good";
    return {
        value: committed === null ? "Not enough data yet" : `${committed} committed`,
        status,
        comparison: committed === null ? "Requires computed sprint metrics." : `${doneCount} done`,
        impact: status === "good" ? "positive" : "negative",
        details: [
            `Committed: ${committed ?? "N/A"}`,
            `In progress: ${inProgress ?? "N/A"}`,
            `Not started: ${notStarted ?? "N/A"}`,
            `Done: ${doneCount}`,
            `Rollover: ${rollover ?? "N/A"}`,
        ],
    };
}
