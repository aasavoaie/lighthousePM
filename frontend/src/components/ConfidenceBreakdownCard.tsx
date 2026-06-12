import type { ConfidenceBreakdown } from "../api/types";
import { confidenceBreakdownStatusLabels, formatConfidenceBreakdownScore } from "./confidenceBreakdown";

interface ConfidenceBreakdownCardProps {
  breakdown: ConfidenceBreakdown;
  title?: string;
}

export function ConfidenceBreakdownCard({ breakdown, title = "Confidence Breakdown" }: ConfidenceBreakdownCardProps) {
  return (
    <section className="confidence-breakdown-card" aria-label={title}>
      <div className="confidence-breakdown-card-heading">
        <h3>{title}</h3>
        <strong>{Math.round(breakdown.totalScore)}%</strong>
      </div>
      <div className="confidence-breakdown-grid">
        {breakdown.components.map((component) => (
          <article className={`metric-card confidence-component status-${component.status}`} key={component.id}>
            <div className="confidence-component-heading">
              <h4>{component.name}</h4>
              <span className={`confidence-breakdown-status confidence-breakdown-status-${component.status}`}>
                {confidenceBreakdownStatusLabels[component.status]}
              </span>
            </div>
            <div className="confidence-component-score-row">
              <strong>{formatConfidenceBreakdownScore(component.score, component.maxScore)}</strong>
              <button
                type="button"
                className="info-button compact-info-button"
                title={component.explanation}
                aria-label={`${component.name} explanation`}
              >
                i
              </button>
            </div>
            <p>{component.explanation}</p>
          </article>
        ))}
      </div>
    </section>
  );
}
