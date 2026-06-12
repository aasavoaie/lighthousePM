import type { RecommendationAction } from "../api/types";
import { filterRecommendations, sortRecommendations } from "./recommendations";

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

assertDeepEqual(
  sortRecommendations(recommendations).map((item) => item.title),
  ["Resolve blockers", "Reduce reopen rate", "Complete committed work"],
  "recommendations sort by confidence gain"
);

assertDeepEqual(
  filterRecommendations(recommendations, "Quality").map((item) => item.title),
  ["Reduce reopen rate"],
  "category filter keeps matching recommendations"
);

assertEqual(filterRecommendations(recommendations, "Flow").length, 0, "filter returns empty state when no category matches");
