import type { RecommendationAction } from "../api/types";

export const recommendationCategories = ["All", "Delivery", "Quality", "Flow", "Risk"] as const;

export type RecommendationFilter = (typeof recommendationCategories)[number];

export function getRecommendationDataDisplay(recommendation: RecommendationAction) {
  const isPartial = recommendation.dataStatus === "PARTIAL";
  return {
    badge: isPartial ? "Partial" : null,
    badgeTitle: isPartial
      ? recommendation.explanations.join(" ") || "This recommendation uses partial metric evidence."
      : null,
    explanations: isPartial ? recommendation.explanations : [],
  };
}

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
