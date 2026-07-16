"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.recommendationCategories = void 0;
exports.sortRecommendations = sortRecommendations;
exports.filterRecommendations = filterRecommendations;
exports.recommendationCategories = ["All", "Delivery", "Quality", "Flow", "Risk"];
function sortRecommendations(recommendations) {
    return [...recommendations].sort((left, right) => right.confidenceImpact - left.confidenceImpact ||
        left.priority - right.priority ||
        left.title.localeCompare(right.title));
}
function filterRecommendations(recommendations, filter) {
    const sorted = sortRecommendations(recommendations);
    if (filter === "All") {
        return sorted;
    }
    return sorted.filter((recommendation) => recommendation.category === filter);
}
