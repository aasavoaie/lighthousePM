import { useMemo, useState } from "react";

import type { RecommendationAction } from "../api/types";
import {
  filterRecommendations,
  recommendationCategories,
  type RecommendationFilter,
} from "./recommendations";

interface RecommendationsPanelProps {
  recommendations: RecommendationAction[];
  title?: string;
  emptyMessage?: string;
}

function formatEffort(value: string) {
  return value.charAt(0).toUpperCase() + value.slice(1);
}

export function RecommendationsPanel({
  recommendations,
  title = "Recommended Actions",
  emptyMessage = "No recommended actions at this confidence level.",
}: RecommendationsPanelProps) {
  const [filter, setFilter] = useState<RecommendationFilter>("All");
  const visibleRecommendations = useMemo(
    () => filterRecommendations(recommendations, filter),
    [recommendations, filter]
  );

  return (
    <section className="recommendations-panel">
      <div className="recommendations-heading">
        <h3>{title}</h3>
        <div className="recommendation-filters" aria-label="Recommendation category filter">
          {recommendationCategories.map((category) => (
            <button
              type="button"
              key={category}
              className={filter === category ? "active" : ""}
              onClick={() => setFilter(category)}
            >
              {category}
            </button>
          ))}
        </div>
      </div>

      {visibleRecommendations.length > 0 ? (
        <div className="recommendation-list">
          {visibleRecommendations.map((recommendation) => (
            <article className="recommendation-row" key={`${recommendation.priority}-${recommendation.title}`}>
              <div className="recommendation-priority" aria-label={`Priority ${recommendation.priority}`}>
                P{recommendation.priority}
              </div>
              <div className="recommendation-content">
                <div className="recommendation-title-row">
                  <strong>{recommendation.title}</strong>
                  <span className="recommendation-impact">Gain +{recommendation.confidenceImpact}</span>
                </div>
                <p>{recommendation.description}</p>
                <dl className="recommendation-meta">
                  <div>
                    <dt>Effort</dt>
                    <dd>{formatEffort(recommendation.effort)}</dd>
                  </div>
                  <div>
                    <dt>Category</dt>
                    <dd>{recommendation.category}</dd>
                  </div>
                </dl>
              </div>
            </article>
          ))}
        </div>
      ) : (
        <p className="muted">{emptyMessage}</p>
      )}
    </section>
  );
}
