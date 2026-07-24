import type { RecommendationAction } from "../api/types";
import {
  filterRecommendations,
  getRecommendationDataDisplay,
  sortRecommendations,
} from "./recommendations";

function assertEqual<T>(actual: T, expected: T, message: string) {
  if (actual !== expected) {
    throw new Error(`${message}: expected ${String(expected)}, received ${String(actual)}`);
  }
}

function assertDeepEqual<T>(actual: T, expected: T, message: string) {
  if (JSON.stringify(actual) !== JSON.stringify(expected)) {
    throw new Error(`${message}: expected ${JSON.stringify(expected)}, received ${JSON.stringify(actual)}`);
  }
}

const recommendations: RecommendationAction[] = [
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

assertDeepEqual(
  sortRecommendations(recommendations).map((item) => item.title),
  ["Resolve blockers", "Reduce reopen events", "Complete committed work"],
  "recommendations sort by confidence gain"
);

assertDeepEqual(
  filterRecommendations(recommendations, "Quality").map((item) => item.title),
  ["Reduce reopen events"],
  "category filter keeps matching recommendations"
);

assertEqual(filterRecommendations(recommendations, "Flow").length, 0, "filter returns empty state when no category matches");

assertDeepEqual(
  getRecommendationDataDisplay(recommendations[2]),
  {
    badge: "Partial",
    badgeTitle: "Reopen evidence is partial.",
    explanations: ["Reopen evidence is partial."],
  },
  "partial recommendation preserves its backend evidence"
);
assertDeepEqual(
  getRecommendationDataDisplay(recommendations[0]),
  { badge: null, badgeTitle: null, explanations: [] },
  "computed recommendation does not display a partial-data warning"
);
