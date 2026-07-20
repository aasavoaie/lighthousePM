"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
const recommendations_1 = require("./recommendations");
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
const recommendations = [
    {
        title: "Complete committed work",
        description: "Finish committed work.",
        priority: 2,
        confidenceImpact: 5,
        effort: "medium",
        category: "Delivery",
        dataStatus: "COMPUTED",
        explanations: [],
    },
    {
        title: "Resolve blockers",
        description: "Clear blockers.",
        priority: 1,
        confidenceImpact: 10,
        effort: "high",
        category: "Risk",
        dataStatus: "COMPUTED",
        explanations: [],
    },
    {
        title: "Reduce reopen events",
        description: "Review reopened work.",
        priority: 3,
        confidenceImpact: 6,
        effort: "medium",
        category: "Quality",
        dataStatus: "PARTIAL",
        explanations: ["Reopen evidence is partial."],
    },
];
assertDeepEqual((0, recommendations_1.sortRecommendations)(recommendations).map((item) => item.title), ["Resolve blockers", "Reduce reopen events", "Complete committed work"], "recommendations sort by confidence gain");
assertDeepEqual((0, recommendations_1.filterRecommendations)(recommendations, "Quality").map((item) => item.title), ["Reduce reopen events"], "category filter keeps matching recommendations");
assertEqual((0, recommendations_1.filterRecommendations)(recommendations, "Flow").length, 0, "filter returns empty state when no category matches");
assertDeepEqual((0, recommendations_1.getRecommendationDataDisplay)(recommendations[2]), {
    badge: "Partial",
    badgeTitle: "Reopen evidence is partial.",
    explanations: ["Reopen evidence is partial."],
}, "partial recommendation preserves its backend evidence");
assertDeepEqual((0, recommendations_1.getRecommendationDataDisplay)(recommendations[0]), { badge: null, badgeTitle: null, explanations: [] }, "computed recommendation does not display a partial-data warning");
