import type { RecommendationAction } from "../api/types";

export const recommendationCategories = ["All", "Delivery", "Quality", "Flow", "Risk"] as const;

export type RecommendationFilter = (typeof recommendationCategories)[number];

export function sortRecommendations(recommendations: RecommendationAction[]) {
  return [...recommendations].sort(
    (left, right) =>
      right.confidenceImpact - left.confidenceImpact ||
      left.priority - right.priority ||
      left.title.localeCompare(right.title)
  );
}

export function filterRecommendations(
  recommendations: RecommendationAction[],
  filter: RecommendationFilter
) {
  const sorted = sortRecommendations(recommendations);
  if (filter === "All") {
    return sorted;
  }
  return sorted.filter((recommendation) => recommendation.category === filter);
}
