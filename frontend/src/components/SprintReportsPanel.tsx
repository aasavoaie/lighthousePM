import type {
  DriverAnalysis,
  SnapshotBaseline,
  SnapshotChangeHistoryResponse,
  SnapshotComparisonResponse,
} from "../api/types";
import { useMetricCatalog } from "../MetricCatalogContext";
import { metricDefinition } from "../metricCatalog";
import { BiggestDriverCard } from "./BiggestDriverCard";
import { MetricColors, MetricLineChart, MetricMultiBarChart } from "./ChartComponents";
import { SnapshotChangePanel } from "./SnapshotChangePanel";
import type { SprintStoryPointUiVisibility } from "./sprintMetrics";
import type {
  RiskHeatmapCell,
  RiskHeatmapStatus,
  SprintChartHistoryPoint,
} from "./sprintCharts";

export type SprintConfidenceRow = {
  [key: string]: string | number | boolean | null | undefined;
  sprint_id: string;
  name: string;
  delivery_confidence: number | null;
  confidence_delta: number | null;
  is_not_closed: boolean;
};

export type SprintCommitmentReliabilityRow = {
  [key: string]: string | number | boolean | null | undefined;
  sprint_id: string;
  name: string;
  committed_story_points: number | null;
  completed_story_points: number | null;
  reliability_pct?: number | null;
  predictability_avg?: number | null;
  is_not_closed: boolean;
};

type SprintReportsPanelProps = {
  isExpanded: boolean;
  storyPointUi: SprintStoryPointUiVisibility;
  storyPointUnavailableMessage: string;
  snapshotComparison: SnapshotComparisonResponse | null;
  snapshotHistory: SnapshotChangeHistoryResponse | null;
  snapshotBaseline: SnapshotBaseline;
  isLoadingSnapshotChanges: boolean;
  snapshotChangeError: string | null;
  biggestDeliveryDriver: DriverAnalysis | null;
  sprintConfidenceRows: SprintConfidenceRow[];
  sprintCommitmentReliabilityRows: SprintCommitmentReliabilityRow[];
  sprintChartRows: SprintChartHistoryPoint[];
  riskHeatmapCells: RiskHeatmapCell[];
  latestConfidenceDelta: number | null;
  isLoadingSprintConfidence: boolean;
  sprintConfidenceError: string | null;
  hasConfidenceTrend: boolean;
  hasConfidenceBreakdown: boolean;
  hasCommitmentTrend: boolean;
  hasReliabilityTrend: boolean;
  hasPredictabilityTrend: boolean;
  hasScopeTrend: boolean;
  hasQualityCountTrend: boolean;
  hasReopenTrend: boolean;
  hasFlowTrend: boolean;
  onToggle: () => void;
  onBaselineChange: (baseline: SnapshotBaseline) => void;
};

const heatmapGroups = ["Delivery", "Quality", "Flow", "Risk"] as const;

const heatmapStatusLabels: Record<RiskHeatmapStatus, string> = {
  healthy: "Healthy",
  watch: "Watch",
  risk: "Risk",
  critical: "Critical",
  neutral: "No data",
};

function formatChartValue(value: number, name: string) {
  const formatted = Number(value.toFixed(2));
  if (
    name.includes("%") ||
    name.includes("Confidence") ||
    name.includes("Reliability") ||
    name.includes("Progress") ||
    name.includes("Velocity") ||
    name.includes("Blocker") ||
    name.includes("Scope Stability") ||
    name.includes("Reopen") ||
    name.includes("Predictability")
  ) {
    return `${formatted}%`;
  }
  if (name.includes("Cycle time")) {
    return `${formatted} days`;
  }
  return String(formatted);
}

function formatDeltaText(delta: number | null) {
  if (delta === null) {
    return null;
  }
  if (delta === 0) {
    return "No change from previous sprint";
  }
  return `${delta > 0 ? "+" : ""}${Number(delta.toFixed(2))}% from previous sprint`;
}

function RiskHeatmap({ rows, cells }: { rows: SprintChartHistoryPoint[]; cells: RiskHeatmapCell[] }) {
  if (rows.length === 0) {
    return <p className="muted">Risk heatmap requires recent sprint metrics.</p>;
  }
  const statusByCell = new Map(cells.map((cell) => [`${cell.group}-${cell.sprint_id}`, cell.status]));

  return (
    <div className="risk-heatmap" role="table" aria-label="Sprint health heatmap">
      <div className="risk-heatmap-row risk-heatmap-header" role="row">
        <span role="columnheader">Area</span>
        {rows.map((row) => <span role="columnheader" key={row.sprint_id}>{row.name}</span>)}
      </div>
      {heatmapGroups.map((group) => (
        <div className="risk-heatmap-row" role="row" key={group}>
          <span className="risk-heatmap-group" role="rowheader">{group}</span>
          {rows.map((row) => {
            const status = statusByCell.get(`${group}-${row.sprint_id}`) ?? "neutral";
            return (
              <span
                className={`risk-heatmap-cell heatmap-${status}`}
                role="cell"
                key={`${group}-${row.sprint_id}`}
                title={`${group}: ${heatmapStatusLabels[status]}`}
              >
                {heatmapStatusLabels[status]}
              </span>
            );
          })}
        </div>
      ))}
    </div>
  );
}

export function SprintReportsPanel({
  isExpanded,
  storyPointUi,
  storyPointUnavailableMessage,
  snapshotComparison,
  snapshotHistory,
  snapshotBaseline,
  isLoadingSnapshotChanges,
  snapshotChangeError,
  biggestDeliveryDriver,
  sprintConfidenceRows,
  sprintCommitmentReliabilityRows,
  sprintChartRows,
  riskHeatmapCells,
  latestConfidenceDelta,
  isLoadingSprintConfidence,
  sprintConfidenceError,
  hasConfidenceTrend,
  hasConfidenceBreakdown,
  hasCommitmentTrend,
  hasReliabilityTrend,
  hasPredictabilityTrend,
  hasScopeTrend,
  hasQualityCountTrend,
  hasReopenTrend,
  hasFlowTrend,
  onToggle,
  onBaselineChange,
}: SprintReportsPanelProps) {
  const catalog = useMetricCatalog();
  const confidenceDeltaText = formatDeltaText(latestConfidenceDelta);

  return (
    <section className="panel charts-panel">
      <div className="panel-heading">
        <h2>Charts</h2>
        <div className="panel-heading-actions">
          <button
            type="button"
            className="secondary-button compact-button"
            aria-expanded={isExpanded}
            onClick={onToggle}
          >
            {isExpanded ? "Minimize" : "Expand"}
          </button>
        </div>
      </div>
      {isExpanded ? (
        <>
          {storyPointUi.showStoryPointUnavailableMessage ? (
            <p className="muted">{storyPointUnavailableMessage}</p>
          ) : null}

          {storyPointUi.hasStoryPointMetrics ? (
            <>
              <SnapshotChangePanel
                context="sprint"
                comparison={snapshotComparison}
                history={snapshotHistory}
                baseline={snapshotBaseline}
                isLoading={isLoadingSnapshotChanges}
                error={snapshotChangeError}
                onBaselineChange={onBaselineChange}
              />

              {biggestDeliveryDriver ? (
                <BiggestDriverCard driver={biggestDeliveryDriver} heading="Biggest Delivery Drag" />
              ) : null}

              <div id="delivery-confidence-history" className="chart-section-heading chart-section-hero">
                <div>
                  <h3>Delivery Confidence Trend</h3>
                  <p className="chart-section-subtitle">
                    Is delivery health improving or slipping across recent sprints?
                  </p>
                </div>
                <div className="chart-heading-meta">
                  {sprintConfidenceRows.length > 0 ? <span className="muted">Last {sprintConfidenceRows.length}</span> : null}
                  {confidenceDeltaText ? <span className="chart-delta-pill">{confidenceDeltaText}</span> : null}
                </div>
              </div>
              {isLoadingSprintConfidence ? <p className="muted">Loading sprint chart history...</p> : null}
              {sprintConfidenceError ? <p className="error-text">{sprintConfidenceError}</p> : null}
              {!isLoadingSprintConfidence && !sprintConfidenceError && !hasConfidenceTrend ? (
                <p className="muted">No sprint confidence data available yet.</p>
              ) : null}
              {!isLoadingSprintConfidence && !sprintConfidenceError && hasConfidenceTrend ? (
                <MetricLineChart
                  data={sprintConfidenceRows}
                  height={380}
                  lines={[{
                    key: "delivery_confidence",
                    label: metricDefinition(catalog, "sprint", "delivery_confidence_score").label,
                    color: MetricColors.sprintConfidence,
                  }]}
                  dataKey="name"
                  formatter={formatChartValue}
                  yDomain={[0, 100]}
                  yTickFormatter={(value) => `${Math.round(value)}%`}
                  referenceLines={[
                    { y: 80, label: "Healthy", color: MetricColors.sprintConfidence },
                    { y: 60, label: "Watch", color: MetricColors.confidenceWatch },
                    { y: 40, label: "Risk", color: MetricColors.confidenceCritical },
                  ]}
                />
              ) : null}

              <div className="chart-section-heading">
                <div>
                  <h3>Confidence Breakdown History</h3>
                  <p className="chart-section-subtitle">
                    Which confidence driver is pushing recent sprints up or down?
                  </p>
                </div>
              </div>
              {!isLoadingSprintConfidence && !sprintConfidenceError && hasConfidenceBreakdown ? (
                <MetricLineChart
                  data={sprintChartRows}
                  lines={[
                    { key: "progress_alignment", label: "Progress Alignment", color: MetricColors.progressAlignment },
                    { key: "velocity_fit", label: "Velocity Fit", color: MetricColors.velocityFit },
                    { key: "scope_stability", label: "Scope Stability", color: MetricColors.scopeStability },
                    { key: "blocker_health", label: "Blocker Health", color: MetricColors.blockerHealth },
                  ]}
                  dataKey="name"
                  formatter={formatChartValue}
                  yDomain={[0, 100]}
                  yTickFormatter={(value) => `${Math.round(value)}%`}
                />
              ) : null}

              <div className="chart-section-heading">
                <div>
                  <h3>Sprint Commitment Reliability</h3>
                  <p className="chart-section-subtitle">
                    Committed vs completed scope, with reliability percent and predictability trend when available.
                  </p>
                </div>
              </div>
              {!isLoadingSprintConfidence && !sprintConfidenceError && !hasCommitmentTrend ? (
                <p className="muted">No sprint commitment reliability data available yet.</p>
              ) : null}
              {!isLoadingSprintConfidence && !sprintConfidenceError && hasCommitmentTrend ? (
                <>
                  <MetricMultiBarChart
                    data={sprintCommitmentReliabilityRows}
                    bars={[
                      { key: "committed_story_points", label: "Committed story points", color: MetricColors.committedScope },
                      { key: "completed_story_points", label: "Completed story points", color: MetricColors.completedScope },
                    ]}
                    dataKey="name"
                    formatter={formatChartValue}
                  />
                  {hasReliabilityTrend ? (
                    <MetricLineChart
                      data={sprintCommitmentReliabilityRows}
                      height={220}
                      lines={[
                        { key: "reliability_pct", label: "Reliability %", color: MetricColors.scopeStability },
                        ...(hasPredictabilityTrend
                          ? [{ key: "predictability_avg", label: "Predictability avg", color: MetricColors.velocityFit }]
                          : []),
                      ]}
                      dataKey="name"
                      formatter={formatChartValue}
                      yDomain={[0, 120]}
                      yTickFormatter={(value) => `${Math.round(value)}%`}
                    />
                  ) : null}
                  {!hasPredictabilityTrend ? (
                    <p className="muted chart-empty-note">Predictability trend requires at least 3 closed sprints.</p>
                  ) : null}
                </>
              ) : null}
            </>
          ) : null}

          {storyPointUi.showStoryPointChartEmptyState ? (
            <>
              <div id="delivery-confidence-history" className="chart-section-heading chart-section-hero">
                <div>
                  <h3>Delivery Confidence Trend</h3>
                  <p className="chart-section-subtitle">
                    Is delivery health improving or slipping across recent sprints?
                  </p>
                </div>
              </div>
              <p className="muted chart-empty-note">{storyPointUnavailableMessage}</p>

              <div className="chart-section-heading">
                <div>
                  <h3>Confidence Breakdown History</h3>
                  <p className="chart-section-subtitle">
                    Which confidence driver is pushing recent sprints up or down?
                  </p>
                </div>
              </div>
              <p className="muted chart-empty-note">{storyPointUnavailableMessage}</p>

              <div className="chart-section-heading">
                <div>
                  <h3>Sprint Commitment Reliability</h3>
                  <p className="chart-section-subtitle">
                    Committed vs completed scope, with reliability percent and predictability trend when available.
                  </p>
                </div>
              </div>
              <p className="muted chart-empty-note">{storyPointUnavailableMessage}</p>
            </>
          ) : null}

          <div className="chart-section-heading">
            <div>
              <h3>Scope Change Trend</h3>
              <p className="chart-section-subtitle">Planning instability across recent sprints.</p>
            </div>
          </div>
          {!isLoadingSprintConfidence && !sprintConfidenceError && hasScopeTrend ? (
            <MetricMultiBarChart
              data={sprintChartRows}
              bars={[
                { key: "scope_change_count", label: "Scope changes", color: MetricColors.scopeChurn },
                { key: "scope_added_count", label: "Addition events", color: MetricColors.completedScope },
                { key: "scope_removed_count", label: "Removal events", color: MetricColors.bugs },
                { key: "net_scope_change", label: "Net scope change", color: MetricColors.neutralRisk },
              ]}
              dataKey="name"
              formatter={formatChartValue}
            />
          ) : null}
          {!isLoadingSprintConfidence && !sprintConfidenceError && !hasScopeTrend ? (
            <p className="muted">Scope change trend requires computed scope-change history.</p>
          ) : null}

          <div className="chart-section-heading">
            <div>
              <h3>Quality Trend</h3>
              <p className="chart-section-subtitle">Sprint-level quality risk signals over time.</p>
            </div>
          </div>
          {!isLoadingSprintConfidence && !sprintConfidenceError && hasQualityCountTrend ? (
            <MetricMultiBarChart
              data={sprintChartRows}
              bars={[
                {
                  key: "open_high_severity_bugs",
                  label: metricDefinition(catalog, "sprint", "open_high_severity_bugs").label,
                  color: MetricColors.bugs,
                },
                {
                  key: "bugs_created_during_sprint",
                  label: metricDefinition(catalog, "sprint", "bugs_created_during_sprint").label,
                  color: MetricColors.confidenceWatch,
                },
              ]}
              dataKey="name"
              formatter={formatChartValue}
            />
          ) : null}
          {!isLoadingSprintConfidence && !sprintConfidenceError && hasReopenTrend ? (
            <MetricLineChart
              data={sprintChartRows}
              height={220}
              lines={[{
                key: "reopen_rate_pct",
                label: metricDefinition(catalog, "sprint", "reopen_rate_pct").label,
                color: MetricColors.reopenRate,
              }]}
              dataKey="name"
              formatter={formatChartValue}
              yDomain={[0, "auto"]}
              yTickFormatter={(value) => `${Math.round(value)}%`}
            />
          ) : null}
          {!isLoadingSprintConfidence && !sprintConfidenceError && !hasQualityCountTrend && !hasReopenTrend ? (
            <p className="muted">Quality trend requires sprint quality history.</p>
          ) : null}

          <div className="chart-section-heading">
            <div>
              <h3>Flow Trend</h3>
              <p className="chart-section-subtitle">Cycle-time history for recent sprints.</p>
            </div>
          </div>
          {!isLoadingSprintConfidence && !sprintConfidenceError && hasFlowTrend ? (
            <MetricLineChart
              data={sprintChartRows}
              lines={[{
                key: "median_cycle_time_days",
                label: metricDefinition(catalog, "sprint", "median_cycle_time_days").label,
                color: MetricColors.cycleTime,
              }]}
              dataKey="name"
              formatter={formatChartValue}
            />
          ) : null}
          {!isLoadingSprintConfidence && !sprintConfidenceError && !hasFlowTrend ? (
            <p className="muted">Flow trend requires cycle-time history.</p>
          ) : null}

          <div className="chart-section-heading">
            <div>
              <h3>Risk Heatmap</h3>
              <p className="chart-section-subtitle">
                Delivery, quality, flow, and risk status across recent sprints.
              </p>
            </div>
          </div>
          {!isLoadingSprintConfidence && !sprintConfidenceError ? (
            <RiskHeatmap rows={sprintChartRows} cells={riskHeatmapCells} />
          ) : null}

          <div className="chart-section-heading">
            <div>
              <h3>Sprint Evolution Timeline</h3>
              <p className="chart-section-subtitle">Selected sprint events and confidence changes.</p>
            </div>
          </div>
          <p className="muted chart-empty-note">Sprint evolution will appear after multiple snapshots are collected.</p>
        </>
      ) : null}
    </section>
  );
}
