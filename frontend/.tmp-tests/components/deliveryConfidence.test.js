"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
const deliveryConfidence_1 = require("./deliveryConfidence");
function assertEqual(actual, expected, message) {
    if (actual !== expected) {
        throw new Error(`${message}: expected ${String(expected)}, received ${String(actual)}`);
    }
}
function assertDeepEqual(actual, expected, message) {
    if (JSON.stringify(actual) !== JSON.stringify(expected)) {
        throw new Error(`${message}: expected ${JSON.stringify(expected)}, received ${JSON.stringify(actual)}`);
    }
}
const moderateComponents = {
    progress_alignment: 41,
    velocity_fit: 52,
    blocker_penalty: 95,
    scope_stability: 70,
};
const healthyComponents = {
    progress_alignment: 90,
    velocity_fit: 88,
    blocker_penalty: 100,
    scope_stability: 84,
};
const progressInputs = {
    committed_issue_count: 8,
    pointed_issue_count: 8,
    initial_commitment_count: 8,
    committed_effective_points: 83,
    completed_effective_points: 14,
    remaining_effective_points: 69,
    completed_scope_pct: 17,
    time_elapsed_pct: 41,
    historical_velocity: 56,
    baseline_sprint_count: 3,
    baseline_sprints: [],
    velocity_status: "COMPUTED",
    remaining_capacity_points: 30,
    blocked_issue_ratio: 0.05,
    scope_change_count: 6,
    scope_added_count: 6,
    scope_removed_count: 0,
    scope_stability_index: 0.75,
    scope_change_issue_keys: [],
    scope_added_issue_keys: [],
    scope_removed_issue_keys: [],
};
assertDeepEqual((0, deliveryConfidence_1.getConfidenceStatus)(80), { level: "healthy", label: "Healthy" }, "80 is healthy");
assertDeepEqual((0, deliveryConfidence_1.getConfidenceStatus)(60), { level: "watch", label: "Watch" }, "60 is watch");
assertDeepEqual((0, deliveryConfidence_1.getConfidenceStatus)(40), { level: "risk", label: "Moderate Risk" }, "40 is moderate risk");
assertDeepEqual((0, deliveryConfidence_1.getConfidenceStatus)(39.99), { level: "critical", label: "High Risk" }, "under 40 is high risk");
assertDeepEqual((0, deliveryConfidence_1.getComponentStatus)(40), { level: "risk", label: "Risk" }, "40 component status is risk");
assertEqual((0, deliveryConfidence_1.getComponentExplanation)("blocker_penalty", 95), "Blocked work is not materially affecting delivery confidence.", "blocker health explains high scores positively");
assertEqual((0, deliveryConfidence_1.getBiggestDrag)(moderateComponents).key, "progress_alignment", "lowest component is biggest drag");
assertDeepEqual((0, deliveryConfidence_1.getRiskDrivers)(moderateComponents), [
    { message: "Progress is behind expected sprint pace.", severity: "warning" },
    { message: "Current pace is below historical velocity.", severity: "warning" },
], "risk drivers are generated from components below 60");
assertDeepEqual((0, deliveryConfidence_1.getRiskDrivers)(healthyComponents), [{ message: "No major delivery confidence risks detected.", severity: "positive" }], "all healthy components produce a positive note");
const progress = (0, deliveryConfidence_1.calculateExpectedVsActualProgress)(progressInputs);
assertEqual(Math.round(progress.expectedProgress ?? 0), 41, "expected progress comes from elapsed percent");
assertEqual(Math.round(progress.actualProgress ?? 0), 17, "actual progress uses completed over committed points");
assertEqual(Math.round(progress.gap ?? 0), -24, "gap is actual minus expected progress");
assertEqual((0, deliveryConfidence_1.getDeliveryConfidenceSummary)(moderateComponents), "Sprint is behind the expected delivery pace. The main confidence drivers are progress alignment and velocity fit. Blocker health remains positive.", "summary is based on the lowest scoring components");
