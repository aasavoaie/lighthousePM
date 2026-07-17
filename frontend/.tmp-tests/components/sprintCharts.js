"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.scopeCreepStatusThresholds = exports.confidenceStatusThresholds = void 0;
exports.calculateReliabilityPct = calculateReliabilityPct;
exports.getConfidenceStatusLevel = getConfidenceStatusLevel;
exports.getSprintGroupHealthStatus = getSprintGroupHealthStatus;
exports.calculateMovingAverage = calculateMovingAverage;
exports.hasChartData = hasChartData;
exports.normalizeScopeChange = normalizeScopeChange;
exports.normalizeQualityTrend = normalizeQualityTrend;
exports.getRiskHeatmapCellStatus = getRiskHeatmapCellStatus;
exports.buildRiskHeatmapRows = buildRiskHeatmapRows;
exports.buildSprintChartHistory = buildSprintChartHistory;
const sprintMetrics_1 = require("./sprintMetrics");
exports.confidenceStatusThresholds = {
    healthy: 80,
    watch: 60,
    risk: 40,
};
exports.scopeCreepStatusThresholds = {
    critical: 20,
    watch: 10,
};
function calculateReliabilityPct(committedStoryPoints, completedStoryPoints) {
    if (committedStoryPoints <= 0) {
        return null;
    }
    return Number(((completedStoryPoints / committedStoryPoints) * 100).toFixed(2));
}
function getConfidenceStatusLevel(confidence) {
    if (confidence >= exports.confidenceStatusThresholds.healthy) {
        return "healthy";
    }
    if (confidence >= exports.confidenceStatusThresholds.watch) {
        return "watch";
    }
    return confidence >= exports.confidenceStatusThresholds.risk ? "risk" : "critical";
}
function getSprintGroupHealthStatus(statuses) {
    if (statuses.some((status) => status === "critical")) {
        return "critical";
    }
    if (statuses.some((status) => status === "risk")) {
        return "risk";
    }
    if (statuses.some((status) => status === "watch")) {
        return "watch";
    }
    if (statuses.some((status) => status === "healthy")) {
        return "healthy";
    }
    return "neutral";
}
function metricStatusToHeatmap(status) {
    if (status === "good") {
        return "healthy";
    }
    if (status === "warning") {
        return "watch";
    }
    if (status === "critical") {
        return "critical";
    }
    return "neutral";
}
function calculateMovingAverage(values, windowSize) {
    return values.map((_, index) => {
        const windowValues = values.slice(Math.max(0, index - windowSize + 1), index + 1).filter((value) => value !== null);
        if (windowValues.length < windowSize) {
            return null;
        }
        return Number((windowValues.reduce((sum, value) => sum + value, 0) / windowValues.length).toFixed(2));
    });
}
function hasChartData(rows, keys) {
    return rows.some((row) => keys.some((key) => row[key] !== null && row[key] !== undefined));
}
function normalizeScopeChange(confidence) {
    const added = confidence.inputs.scope_added_count;
    const removed = confidence.inputs.scope_removed_count;
    return {
        scope_change_count: confidence.inputs.scope_change_count,
        scope_creep_pct: confidence.inputs.scope_stability_index === null
            ? null
            : Number((confidence.inputs.scope_stability_index * 100).toFixed(2)),
        scope_added_count: added,
        scope_removed_count: removed,
        net_scope_change: added - removed,
    };
}
function normalizeQualityTrend(metrics) {
    return {
        open_high_severity_bugs: metrics.open_high_severity_bugs,
        bugs_created_during_sprint: metrics.bugs_created_during_sprint,
        reopen_rate_pct: metrics.reopen_rate_pct,
    };
}
function scopeCreepStatus(scopeCreepPct) {
    if (scopeCreepPct === null) {
        return "neutral";
    }
    if (scopeCreepPct > exports.scopeCreepStatusThresholds.critical) {
        return "critical";
    }
    if (scopeCreepPct > exports.scopeCreepStatusThresholds.watch) {
        return "watch";
    }
    return "healthy";
}
function effectiveStatus(...statuses) {
    return getSprintGroupHealthStatus(statuses);
}
function getRiskHeatmapCellStatus(group, row) {
    if (group === "Delivery") {
        return row.delivery_status;
    }
    if (group === "Quality") {
        return row.quality_status;
    }
    if (group === "Flow") {
        return row.flow_status;
    }
    return row.risk_status;
}
function buildRiskHeatmapRows(rows) {
    const groups = ["Delivery", "Quality", "Flow", "Risk"];
    return rows.flatMap((row) => groups.map((group) => ({
        sprint_id: row.sprint_id,
        sprint_name: row.name,
        group,
        status: getRiskHeatmapCellStatus(group, row),
    })));
}
function baseChartRow(source) {
    const { metrics } = source;
    if (!metrics.is_computed) {
        return null;
    }
    const confidence = (0, sprintMetrics_1.hasSprintStoryPoints)(metrics) ? metrics.delivery_confidence : null;
    const scope = confidence
        ? normalizeScopeChange(confidence)
        : {
            scope_change_count: 0,
            scope_creep_pct: null,
            scope_added_count: 0,
            scope_removed_count: 0,
            net_scope_change: 0,
        };
    const quality = normalizeQualityTrend(metrics.metrics);
    const committed = confidence ? Number(confidence.inputs.committed_effective_points.toFixed(2)) : null;
    const completed = confidence ? Number(confidence.inputs.completed_effective_points.toFixed(2)) : null;
    const reliability = committed !== null && completed !== null ? calculateReliabilityPct(committed, completed) : null;
    const deliveryStatus = effectiveStatus(confidence ? getConfidenceStatusLevel(confidence.score) : "neutral", metricStatusToHeatmap((0, sprintMetrics_1.getMetricStatus)("completed_scope_pct", metrics.metrics.completed_scope_pct)), scopeCreepStatus(scope.scope_creep_pct));
    return {
        sprint_id: source.sprint_id,
        name: source.name,
        is_not_closed: source.is_not_closed,
        ruleset_version: metrics.ruleset_version ?? 0,
        version_boundary: false,
        delivery_confidence: confidence ? Number(confidence.score.toFixed(2)) : null,
        confidence_delta: null,
        progress_alignment: confidence ? Number(confidence.components.progress_alignment.toFixed(2)) : null,
        velocity_fit: confidence ? Number(confidence.components.velocity_fit.toFixed(2)) : null,
        blocker_health: confidence ? Number(confidence.components.blocker_penalty.toFixed(2)) : null,
        scope_stability: confidence ? Number(confidence.components.scope_stability.toFixed(2)) : null,
        committed_story_points: committed,
        completed_story_points: completed,
        reliability_pct: reliability,
        predictability_avg: null,
        ...scope,
        ...quality,
        median_cycle_time_days: metrics.metrics.median_cycle_time_days,
        delivery_status: deliveryStatus,
        quality_status: effectiveStatus(metricStatusToHeatmap((0, sprintMetrics_1.getMetricStatus)("open_high_severity_bugs", metrics.metrics.open_high_severity_bugs)), metricStatusToHeatmap((0, sprintMetrics_1.getMetricStatus)("bugs_created_during_sprint", metrics.metrics.bugs_created_during_sprint)), metricStatusToHeatmap((0, sprintMetrics_1.getMetricStatus)("reopen_rate_pct", metrics.metrics.reopen_rate_pct))),
        flow_status: metricStatusToHeatmap((0, sprintMetrics_1.getMetricStatus)("median_cycle_time_days", metrics.metrics.median_cycle_time_days)),
        risk_status: effectiveStatus(metricStatusToHeatmap((0, sprintMetrics_1.getMetricStatus)("open_blockers", metrics.metrics.open_blockers)), metricStatusToHeatmap((0, sprintMetrics_1.getMetricStatus)("rollover_count", metrics.metrics.rollover_count))),
    };
}
function buildSprintChartHistory(sources) {
    const rows = sources.map(baseChartRow).filter((row) => row !== null);
    const closedReliabilityValues = [];
    return rows.map((row, index) => {
        const previousConfidence = index === 0 ? null : rows[index - 1].delivery_confidence;
        const versionBoundary = index > 0 && rows[index - 1].ruleset_version !== row.ruleset_version;
        return {
            ...row,
            version_boundary: versionBoundary,
            confidence_delta: versionBoundary || row.delivery_confidence === null || previousConfidence === null
                ? null
                : Number((row.delivery_confidence - previousConfidence).toFixed(2)),
            predictability_avg: (() => {
                if (row.is_not_closed || row.reliability_pct === null) {
                    return null;
                }
                closedReliabilityValues.push(row.reliability_pct);
                if (closedReliabilityValues.length < 3) {
                    return null;
                }
                const recent = closedReliabilityValues.slice(-3);
                return Number((recent.reduce((sum, value) => sum + value, 0) / recent.length).toFixed(2));
            })(),
        };
    });
}
