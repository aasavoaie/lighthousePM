import type {
  DeliveryConfidenceDetail,
  SprintIssue,
  SprintMetricValues,
  SprintMetricsResponse,
} from "../api/types";
import { useMetricCatalog } from "../MetricCatalogContext";
import {
  fallbackMetricCatalog,
  formatCatalogMetricValue,
  metricDefinition,
  type MetricPresentationDefinition,
} from "../metricCatalog";
import {
  MetricCategorySection,
  MetricStatusCard,
  type MetricImpact,
  type MetricStatus,
} from "./MetricCards";
import {
  formatPercent,
  getGroupSummary,
  getMetricStatus,
  getSprintMetricDisplay,
  type MetricEvaluation,
  type PredictabilityDisplayModel,
  type ScopeCreepDisplayModel,
  type SprintWorkStateDisplayModel,
  type VelocityHealthDisplayModel,
  type WorkDistributionDisplayModel,
} from "./sprintMetrics";

type SprintMetricsPanelProps = {
  metrics: SprintMetricsResponse | null;
  deliveryConfidence: DeliveryConfidenceDetail | null;
  issuesByKey: Record<string, SprintIssue>;
  metricEvaluations: MetricEvaluation[];
  focusAreas: string[];
  scopeCreepCard: ScopeCreepDisplayModel | null;
  velocityHealthCard: VelocityHealthDisplayModel | null;
  predictabilityCard: PredictabilityDisplayModel | null;
  workDistributionCard: WorkDistributionDisplayModel;
  sprintWorkStateCard: SprintWorkStateDisplayModel | null;
  isLoading: boolean;
  isExpanded: boolean;
  onToggle: () => void;
  onSelectIssue: (issueKey: string) => void;
};

const sprintCardMetricFields = new Set<keyof SprintMetricValues>([
  "committed_scope",
  "completed_scope_pct",
  "open_blockers",
  "open_high_severity_bugs",
  "bugs_created_during_sprint",
  "rollover_count",
  "median_cycle_time_days",
  "reopen_rate_pct",
]);

function getIssueStatusClass(issueKey: string, issuesByKey: Record<string, SprintIssue>) {
  const status = issuesByKey[issueKey]?.status?.trim().toLowerCase() ?? "";
  if (status === "blocked") {
    return "blocked";
  }
  if (status === "done" || status === "closed" || status === "resolved") {
    return "done";
  }
  if (status === "in progress" || status === "in development" || status === "in review" || status === "in testing") {
    return "in-progress";
  }
  return "todo";
}

function renderScopeIssueKeys(
  label: string,
  issueKeys: string[],
  issuesByKey: Record<string, SprintIssue>,
  onSelectIssue: (issueKey: string) => void,
  hiddenIssueCount = 0
) {
  if (issueKeys.length === 0 && hiddenIssueCount === 0) {
    return null;
  }
  return (
    <div className="scope-ticket-group">
      <span className="muted">{label}</span>
      <ul className="metric-ticket-list" aria-label={`${label} tickets`}>
        {issueKeys.map((issueKey) => (
          <li key={issueKey}>
            <button
              type="button"
              className={`link-button status-badge ${getIssueStatusClass(issueKey, issuesByKey)}`}
              onClick={() => onSelectIssue(issueKey)}
            >
              {issueKey}
            </button>
          </li>
        ))}
        {hiddenIssueCount > 0 ? (
          <li>
            <span className="status-badge overflow-badge">+{hiddenIssueCount} more</span>
          </li>
        ) : null}
      </ul>
    </div>
  );
}

function renderMetricIssueKeys(
  metricName: keyof SprintMetricValues,
  value: number | null,
  metrics: SprintMetricsResponse,
  issuesByKey: Record<string, SprintIssue>,
  onSelectIssue: (issueKey: string) => void,
  label: string,
) {
  if (
    metricName !== "open_blockers" &&
    metricName !== "open_high_severity_bugs" &&
    metricName !== "bugs_created_during_sprint"
  ) {
    return null;
  }

  const issueKeys = metrics.metric_issue_keys[metricName] ?? [];
  if (issueKeys.length === 0) {
    return value !== null && value > 0 ? <p className="metric-ticket-empty">Recompute to populate ticket list.</p> : null;
  }

  return (
    <ul className="metric-ticket-list" aria-label={`${label} tickets`}>
      {issueKeys.map((issueKey) => (
        <li key={issueKey}>
          <button
            type="button"
            className={`link-button status-badge ${getIssueStatusClass(issueKey, issuesByKey)}`}
            onClick={() => onSelectIssue(issueKey)}
          >
            {issueKey}
          </button>
        </li>
      ))}
    </ul>
  );
}

function getMetricImpact(status: MetricStatus): MetricImpact {
  if (status === "good") {
    return "positive";
  }
  if (status === "critical" || status === "warning") {
    return "negative";
  }
  return "unknown";
}

function getMetricContext(
  metricName: keyof SprintMetricValues,
  metrics: SprintMetricsResponse,
  confidence: DeliveryConfidenceDetail | null,
  definition: MetricPresentationDefinition,
) {
  const value = metrics.metrics[metricName];
  if (value === null) {
    return "Not enough data yet";
  }
  if (metricName === "completed_scope_pct") {
    if (confidence) {
      return `${Number(confidence.inputs.completed_effective_points.toFixed(2))} of ${Number(confidence.inputs.committed_effective_points.toFixed(2))} pts completed`;
    }
    return `${formatPercent(value)} of current sprint scope is done`;
  }
  if (metricName === "open_blockers") {
    return value === 0 ? "No open blockers" : `${value} open blockers`;
  }
  if (metricName === "open_high_severity_bugs") {
    return value === 0 ? "No open high-severity bugs" : `${value} open high-severity bugs`;
  }
  if (metricName === "bugs_created_during_sprint") {
    return value === 0 ? "No sprint-created bugs" : `${value} bugs created in sprint window`;
  }
  if (metricName === "median_cycle_time_days") {
    return `${formatCatalogMetricValue(definition, value)} day median cycle time`;
  }
  if (metricName === "reopen_rate_pct") {
    return value === 0
      ? "No reopen events among eligible tickets"
      : `${formatPercent(value)} (${value.toFixed(2)} reopen events per 100 eligible tickets)`;
  }
  if (metricName === "rollover_count") {
    return value === 0
      ? "No unfinished tickets in the closed sprint scope"
      : `${value} current closed-sprint tickets unfinished`;
  }
  return definition.label;
}

export function buildBaseMetricEvaluation(
  metricName: keyof SprintMetricValues,
  metrics: SprintMetricsResponse,
  definition = metricDefinition(fallbackMetricCatalog, "sprint", metricName),
): MetricEvaluation {
  const value = metrics.metrics[metricName];
  const status = getMetricStatus(metricName, value);
  const formattedValue = formatCatalogMetricValue(definition, value);
  const label = definition.label;
  const group: MetricEvaluation["group"] = definition.category;

  let focusMessage = `${label} needs attention.`;
  if (metricName === "completed_scope_pct") {
    focusMessage = `Completed scope is ${status === "critical" ? "critical" : "at watch level"} at ${formattedValue}.`;
  } else if (metricName === "open_high_severity_bugs") {
    focusMessage = "Open high-severity bugs require attention.";
  } else if (metricName === "open_blockers") {
    focusMessage = "Open blockers require attention.";
  } else if (metricName === "rollover_count") {
    focusMessage = `Unfinished closed-sprint scope is ${formattedValue}.`;
  } else if (metricName === "reopen_rate_pct") {
    focusMessage = `Reopen events per 100 eligible tickets are ${formattedValue}.`;
  } else if (metricName === "median_cycle_time_days") {
    focusMessage = `Median cycle time is ${formattedValue} days.`;
  } else if (metricName === "bugs_created_during_sprint") {
    focusMessage = "Sprint-created bugs are adding quality load.";
  }

  return { key: metricName, label, group, status, value, formattedValue, focusMessage };
}

export function SprintMetricsPanel({
  metrics,
  deliveryConfidence,
  issuesByKey,
  metricEvaluations,
  focusAreas,
  scopeCreepCard,
  velocityHealthCard,
  predictabilityCard,
  workDistributionCard,
  sprintWorkStateCard,
  isLoading,
  isExpanded,
  onToggle,
  onSelectIssue,
}: SprintMetricsPanelProps) {
  const catalog = useMetricCatalog();

  function renderSprintMetricCard(metricName: keyof SprintMetricValues) {
    if (!metrics || metricName === "delivery_confidence_score") {
      return null;
    }
    const value = metrics.metrics[metricName];
    const definition = metricDefinition(catalog, "sprint", metricName);
    const availabilityDisplay = getSprintMetricDisplay(metrics, metricName);
    const availabilityExplanations = availabilityDisplay.explanations.filter(
      (explanation) => explanation !== availabilityDisplay.reason
    );
    const missingStatusDetail = availabilityDisplay.missingIssueKeys.length > 0
      ? `Missing status: ${availabilityDisplay.missingIssueKeys.join(", ")}`
      : null;
    const status = availabilityDisplay.isAvailable ? getMetricStatus(metricName, value) : "neutral";
    return (
      <MetricStatusCard
        key={metricName}
        title={definition.label}
        value={availabilityDisplay.value ?? formatCatalogMetricValue(definition, value)}
        status={status}
        comparison={getMetricContext(metricName, metrics, deliveryConfidence, definition)}
        comparisonImpact={getMetricImpact(status)}
        details={[
          ...(availabilityDisplay.reason ? [availabilityDisplay.reason] : []),
          ...availabilityExplanations,
          ...(missingStatusDetail ? [missingStatusDetail] : []),
        ]}
        infoText={availabilityDisplay.reason ?? definition.description}
        badge={availabilityDisplay.badge}
        badgeTitle={availabilityDisplay.reason}
      >
        {renderMetricIssueKeys(metricName, value, metrics, issuesByKey, onSelectIssue, definition.label)}
      </MetricStatusCard>
    );
  }

  function renderCatalogSprintMetrics(category: MetricEvaluation["group"]) {
    return catalog.sprint
      .filter((definition) => definition.category === category)
      .filter((definition) => sprintCardMetricFields.has(definition.api_field as keyof SprintMetricValues))
      .map((definition) => renderSprintMetricCard(definition.api_field as keyof SprintMetricValues));
  }

  return (
    <section className="panel metrics-panel">
      <div className="panel-heading">
        <h2>Metrics</h2>
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
          {isLoading ? <p className="muted">Loading sprint metrics...</p> : null}
          {!isLoading && metrics && !metrics.is_computed ? (
            <p className="muted">Sprint metrics have not been computed yet.</p>
          ) : null}
          {!isLoading && metrics?.is_computed ? (
            <div className="metric-category-stack">
              <section className="focus-areas-section">
                <h3>Focus Areas</h3>
                <ol className="focus-area-list">
                  {focusAreas.map((area) => <li key={area}>{area}</li>)}
                </ol>
              </section>
              <MetricCategorySection title="Delivery" summary={getGroupSummary("delivery", metricEvaluations)}>
                {renderCatalogSprintMetrics("delivery")}
                {scopeCreepCard ? (
                  <MetricStatusCard
                    title="Scope creep"
                    value={scopeCreepCard.value}
                    status={scopeCreepCard.status}
                    comparison={scopeCreepCard.comparison}
                    comparisonImpact={scopeCreepCard.impact}
                    details={scopeCreepCard.details}
                    infoText="High scope creep reduces predictability."
                  >
                    {renderScopeIssueKeys(
                      "Affected issues",
                      scopeCreepCard.issueKeys,
                      issuesByKey,
                      onSelectIssue,
                      scopeCreepCard.hiddenIssueCount
                    )}
                  </MetricStatusCard>
                ) : null}
                {velocityHealthCard ? (
                  <MetricStatusCard
                    title="Velocity health"
                    value={velocityHealthCard.value}
                    status={velocityHealthCard.status}
                    comparison={velocityHealthCard.comparison}
                    comparisonImpact={velocityHealthCard.impact}
                    details={velocityHealthCard.details}
                    infoText="Compares current completed work to historical sprint velocity."
                  />
                ) : null}
                {predictabilityCard ? (
                  <MetricStatusCard
                    title="Team predictability"
                    value={predictabilityCard.value}
                    status={predictabilityCard.status}
                    comparison={predictabilityCard.comparison}
                    comparisonImpact={predictabilityCard.impact}
                    details={predictabilityCard.details}
                    infoText="Shows how reliably recent closed sprints completed committed work."
                  />
                ) : null}
              </MetricCategorySection>
              <MetricCategorySection title="Quality" summary={getGroupSummary("quality", metricEvaluations)}>
                {renderCatalogSprintMetrics("quality")}
              </MetricCategorySection>
              <MetricCategorySection title="Flow" summary={getGroupSummary("flow", metricEvaluations)}>
                {renderCatalogSprintMetrics("flow")}
              </MetricCategorySection>
              <MetricCategorySection title="Risk" summary={getGroupSummary("risk", metricEvaluations)}>
                {renderCatalogSprintMetrics("risk")}
                <MetricStatusCard
                  title={workDistributionCard.title}
                  value={workDistributionCard.value}
                  status={workDistributionCard.status}
                  comparison={workDistributionCard.comparison}
                  comparisonImpact={workDistributionCard.impact}
                  details={workDistributionCard.details}
                  badge={workDistributionCard.badge}
                  badgeTitle={workDistributionCard.badgeTitle}
                  infoText={metricDefinition(catalog, "sprint", "workload_concentration_pct").description}
                />
              </MetricCategorySection>
              {sprintWorkStateCard ? (
                <MetricCategorySection title="Sprint Work State" summary={getGroupSummary("snapshot", metricEvaluations)}>
                  <MetricStatusCard
                    title="Sprint work state"
                    value={sprintWorkStateCard.value}
                    status={sprintWorkStateCard.status}
                    comparison={sprintWorkStateCard.comparison}
                    comparisonImpact={sprintWorkStateCard.impact}
                    details={sprintWorkStateCard.details}
                    infoText="Condenses current sprint scope, in-progress, not-started, done, and applicable unfinished closed-sprint work into one scan-friendly card."
                    badge={sprintWorkStateCard.badge}
                    badgeTitle={sprintWorkStateCard.badgeTitle}
                  />
                </MetricCategorySection>
              ) : null}
            </div>
          ) : null}
        </>
      ) : null}
    </section>
  );
}
