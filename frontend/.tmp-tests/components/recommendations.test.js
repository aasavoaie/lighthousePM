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
    },
    {
        title: "Resolve blockers",
        description: "Clear blockers.",
        priority: 1,
        confidenceImpact: 10,
        effort: "high",
        category: "Risk",
    },
    {
        title: "Reduce reopen rate",
        description: "Review reopened work.",
        priority: 3,
        confidenceImpact: 6,
        effort: "medium",
        category: "Quality",
    },
];
assertDeepEqual((0, recommendations_1.sortRecommendations)(recommendations).map((item) => item.title), ["Resolve blockers", "Reduce reopen rate", "Complete committed work"], "recommendations sort by confidence gain");
assertDeepEqual((0, recommendations_1.filterRecommendations)(recommendations, "Quality").map((item) => item.title), ["Reduce reopen rate"], "category filter keeps matching recommendations");
assertEqual((0, recommendations_1.filterRecommendations)(recommendations, "Flow").length, 0, "filter returns empty state when no category matches");
