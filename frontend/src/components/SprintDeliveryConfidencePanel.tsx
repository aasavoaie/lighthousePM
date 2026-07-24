import type {
  ConfidenceBreakdown,
  DeliveryConfidenceDetail,
  DriverAnalysis,
  SprintMetricsResponse,
} from "../api/types";
import { useMetricCatalog } from "../MetricCatalogContext";
import { metricDefinition } from "../metricCatalog";
import { BiggestDriverCard } from "./BiggestDriverCard";
import { ConfidenceBreakdownCard } from "./ConfidenceBreakdownCard";
import {
  calculateExpectedVsActualProgress,
  formatConfidencePercent,
  getBiggestDrag,
  getConfidenceStatus,
  getDeliveryConfidenceSummary,
  getRiskDrivers,
  roundPercent,
} from "./deliveryConfidence";
import { RecommendationsPanel } from "./RecommendationsPanel";

type SprintDeliveryConfidencePanelProps = {
  metrics: SprintMetricsResponse | null;
  deliveryConfidence: DeliveryConfidenceDetail | null;
  confidenceBreakdown: ConfidenceBreakdown | null;
  biggestDeliveryDriver: DriverAnalysis | null;
  storyPointExplanations: string[];
  missingIssueKeys: string[];
  showUnavailableMessage: boolean;
  isLoading: boolean;
  isExpanded: boolean;
  onToggle: () => void;
};

function SprintDeliveryConfidenceDetails({ confidence }: { confidence: DeliveryConfidenceDetail }) {
  const biggestDrag = getBiggestDrag(confidence.components);
  const progress = calculateExpectedVsActualProgress(confidence.inputs);
  const riskDrivers = getRiskDrivers(confidence.components);

  function formatProgressValue(value: number | null) {
    return value === null ? "N/A" : `${roundPercent(value)}%`;
  }

  function formatPoints(value: number) {
    return `${Math.round(value)} pts`;
  }

  function formatSnapshotPercent(value: number | null | undefined) {
    return value === null || value === undefined ? "N/A" : `${roundPercent(value)}%`;
  }

  function formatBlockedWork(value: number) {
    return `${roundPercent(value * 100)}%`;
  }

  return (
    <div className="confidence-decision-layout">
      <article className={`confidence-callout confidence-callout-${biggestDrag.status.level}`}>
        <h3>Biggest Drag</h3>
        <p>{biggestDrag.label} is the largest contributor to reduced confidence.</p>
      </article>

      <section className="confidence-section">
        <div className="confidence-section-heading">
          <h3>Expected vs Actual Progress</h3>
        </div>
        <dl className="confidence-progress-grid">
          <div>
            <dt>Expected</dt>
            <dd>{formatProgressValue(progress.expectedProgress)}</dd>
          </div>
          <div>
            <dt>Actual</dt>
            <dd>{formatProgressValue(progress.actualProgress)}</dd>
          </div>
          <div>
            <dt>Gap</dt>
            <dd className={progress.gap !== null && progress.gap < 0 ? "confidence-value-danger" : undefined}>
              {formatProgressValue(progress.gap)}
            </dd>
          </div>
        </dl>
      </section>

      <section className="confidence-section">
        <div className="confidence-section-heading">
          <h3>Risk Drivers</h3>
        </div>
        {riskDrivers.length > 0 ? (
          <ul className="confidence-risk-list">
            {riskDrivers.map((driver) => (
              <li className={`confidence-risk-driver risk-${driver.severity}`} key={driver.message}>
                <span className="confidence-risk-icon" aria-hidden="true" />
                {driver.message}
              </li>
            ))}
          </ul>
        ) : (
          <p className="muted">No threshold-based risk drivers detected.</p>
        )}
      </section>

      <section className="confidence-section">
        <div className="confidence-section-heading">
          <h3>Sprint Snapshot</h3>
        </div>
        <dl className="confidence-inputs">
          <dt>Current pointed scope</dt>
          <dd>{formatPoints(confidence.inputs.committed_effective_points)}</dd>
          <dt>Completed scope</dt>
          <dd>{formatPoints(confidence.inputs.completed_effective_points)}</dd>
          <dt>Remaining scope</dt>
          <dd>{formatPoints(confidence.inputs.remaining_effective_points)}</dd>
          <dt>Sprint elapsed</dt>
          <dd>{formatSnapshotPercent(confidence.inputs.time_elapsed_pct)}</dd>
          <dt>Historical velocity</dt>
          <dd>{confidence.inputs.historical_velocity === null ? "N/A" : formatPoints(confidence.inputs.historical_velocity)}</dd>
          <dt>Scope changes</dt>
          <dd>{Math.round(confidence.inputs.scope_change_count)}</dd>
          <dt>Blocked work</dt>
          <dd>{formatBlockedWork(confidence.inputs.blocked_issue_ratio)}</dd>
        </dl>
      </section>

      <section className="confidence-section confidence-trend-placeholder">
        <div className="confidence-section-heading">
          <h3>Delivery confidence in this sprint</h3>
        </div>
        <p className="muted">Confidence trend will appear after multiple snapshots are collected.</p>
      </section>
    </div>
  );
}

export function SprintDeliveryConfidencePanel({
  metrics,
  deliveryConfidence,
  confidenceBreakdown,
  biggestDeliveryDriver,
  storyPointExplanations,
  missingIssueKeys,
  showUnavailableMessage,
  isLoading,
  isExpanded,
  onToggle,
}: SprintDeliveryConfidencePanelProps) {
  const catalog = useMetricCatalog();
  const confidenceDefinition = metricDefinition(catalog, "sprint", "delivery_confidence_score");
  const deliveryConfidenceStatus = deliveryConfidence ? getConfidenceStatus(deliveryConfidence.score) : null;

  return (
    <section className="panel delivery-confidence-panel">
      <div className="panel-heading">
        <div className="delivery-confidence-heading">
          <h2 className="delivery-confidence-title">
            {confidenceDefinition.label}
            <button
              type="button"
              className="info-button"
              title={confidenceDefinition.description}
              aria-label={`${confidenceDefinition.label} info`}
            >
              i
            </button>
          </h2>
          {deliveryConfidence && deliveryConfidenceStatus ? (
            <div
              className="delivery-confidence-decision"
              aria-label={`Delivery confidence ${formatConfidencePercent(deliveryConfidence.score)}, ${deliveryConfidenceStatus.label}`}
            >
              <strong className={`delivery-confidence-score confidence-status-text-${deliveryConfidenceStatus.level}`}>
                {formatConfidencePercent(deliveryConfidence.score)}
              </strong>
              <span className={`confidence-status-pill confidence-status-${deliveryConfidenceStatus.level}`}>
                {deliveryConfidenceStatus.label}
              </span>
            </div>
          ) : null}
        </div>
        <div className="panel-heading-actions">
          {metrics?.ruleset_label ? <span className="muted">{metrics.ruleset_label}</span> : null}
          {deliveryConfidence ? (
            <button
              type="button"
              className="secondary-button compact-button"
              aria-expanded={isExpanded}
              onClick={onToggle}
            >
              {isExpanded ? "Minimize" : "Expand"}
            </button>
          ) : null}
        </div>
      </div>
      {isLoading ? <p className="muted">Loading delivery confidence...</p> : null}
      {!isLoading && metrics && !metrics.is_computed ? (
        <p className="muted">Sprint metrics have not been computed yet.</p>
      ) : null}
      {!isLoading && showUnavailableMessage ? (
        <div className="muted">
          {metrics?.delivery_confidence_status === "INCONCLUSIVE" ? (
            <p>
              <span className="metric-muted-badge">Inconclusive</span>
            </p>
          ) : null}
          {storyPointExplanations.map((explanation) => <p key={explanation}>{explanation}</p>)}
          {missingIssueKeys.length > 0 ? <p>Missing evidence: {missingIssueKeys.join(", ")}</p> : null}
        </div>
      ) : null}
      {!isLoading && deliveryConfidence ? (
        <p className="delivery-confidence-summary">
          {getDeliveryConfidenceSummary(deliveryConfidence.components)}
        </p>
      ) : null}
      {!isLoading && confidenceBreakdown ? <ConfidenceBreakdownCard breakdown={confidenceBreakdown} /> : null}
      {!isLoading && biggestDeliveryDriver ? (
        <BiggestDriverCard driver={biggestDeliveryDriver} heading="Biggest Delivery Drag" />
      ) : null}
      {!isLoading && metrics ? (
        <RecommendationsPanel recommendations={metrics.recommendations} title="Sprint Recommended Actions" />
      ) : null}
      {!isLoading && deliveryConfidence && isExpanded ? (
        <SprintDeliveryConfidenceDetails confidence={deliveryConfidence} />
      ) : null}
    </section>
  );
}
