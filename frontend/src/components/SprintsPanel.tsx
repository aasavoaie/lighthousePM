import { useEffect, useMemo, useState } from "react";
import { apiClient } from "../api/client";
import type {
  Sprint,
  SprintIssue,
  SprintMetricsResponse,
  SnapshotBaseline,
  SnapshotChangeHistoryResponse,
  SnapshotComparisonResponse,
} from "../api/types";
import { useMetricCatalog } from "../MetricCatalogContext";
import { catalogMetricStatus, metricDefinition } from "../metricCatalog";
import { SprintDeliveryConfidencePanel } from "./SprintDeliveryConfidencePanel";
import { SprintHealthPanel, type SprintOption } from "./SprintHealthPanel";
import { buildBaseMetricEvaluation, SprintMetricsPanel } from "./SprintMetricsPanel";
import { SprintReportExportPanel } from "./SprintReportExportPanel";
import {
  SprintReportsPanel,
  type SprintCommitmentReliabilityRow,
  type SprintConfidenceRow,
} from "./SprintReportsPanel";
import { SprintTicketSituationPanel } from "./SprintTicketSituationPanel";
import {
  buildPredictabilityDisplayModel,
  buildScopeCreepDisplayModel,
  buildSprintWorkStateDisplayModel,
  buildSprintStoryPointUiVisibility,
  buildVelocityHealthDisplayModel,
  buildWorkDistributionDisplayModel,
  generateFocusAreas,
  getSprintStoryPointUnavailableReason,
  type MetricEvaluation,
} from "./sprintMetrics";
import {
  buildRiskHeatmapRows,
  buildSprintChartHistory,
  hasChartData,
  type SprintChartHistoryPoint,
} from "./sprintCharts";

type SprintsPanelMode = "intelligence" | "reports";

interface SprintsPanelProps {
  refreshNonce: number;
  onSelectIssue: (issueKey: string) => void;
  mode?: SprintsPanelMode;
  projectKey?: string | null;
}

const sprintIssuePageSize = 100;

function normalizeProjectKey(projectKey: string | null | undefined) {
  const normalized = projectKey?.trim().toUpperCase();
  return normalized ? normalized : null;
}

function sprintMatchesProject(sprint: Sprint | null, projectKey: string | null) {
  if (!sprint || !projectKey) {
    return false;
  }
  return normalizeProjectKey(sprint.project_key) === projectKey;
}

function buildOptions(currentSprint: Sprint | null, closedSprints: Sprint[]): SprintOption[] {
  const options: SprintOption[] = [];
  if (currentSprint) {
    options.push({ label: `Current: ${currentSprint.name}`, sprint: currentSprint });
  }
  for (const sprint of closedSprints) {
    options.push({ label: `Closed: ${sprint.name}`, sprint });
  }
  return options;
}

function sprintSortTime(sprint: Sprint) {
  const primaryDate = sprint.complete_date ?? sprint.end_date ?? sprint.start_date ?? sprint.created_at;
  const parsed = Date.parse(primaryDate);
  return Number.isFinite(parsed) ? parsed : 0;
}

function getRecentSprints(sprints: Sprint[]) {
  return [...sprints]
    .sort((left, right) => sprintSortTime(right) - sprintSortTime(left))
    .slice(0, 5)
    .reverse();
}

function isNotClosedSprint(sprint: Sprint) {
  return sprint.state.trim().toLowerCase() !== "closed";
}

async function loadAllSprintIssues(sprintId: string) {
  const items: SprintIssue[] = [];
  let fetchedCount = 0;
  let total = 0;

  while (true) {
    const response = await apiClient.getSprintIssues(sprintId, fetchedCount, sprintIssuePageSize);
    total = response.total;
    items.push(...response.items);
    fetchedCount += response.items.length;
    if (fetchedCount >= total || response.items.length === 0) {
      break;
    }
  }

  return items;
}

export function SprintsPanel({ refreshNonce, onSelectIssue, mode = "intelligence", projectKey = null }: SprintsPanelProps) {
  const catalog = useMetricCatalog();
  const deliveryConfidenceDefinition = metricDefinition(catalog, "sprint", "delivery_confidence_score");
  const scopeCreepDefinition = metricDefinition(catalog, "sprint", "scope_creep_pct");
  const activeProjectKey = normalizeProjectKey(projectKey);
  const [currentSprint, setCurrentSprint] = useState<Sprint | null>(null);
  const [closedSprints, setClosedSprints] = useState<Sprint[]>([]);
  const [selectedSprintId, setSelectedSprintId] = useState<string | null>(null);
  const [metrics, setMetrics] = useState<SprintMetricsResponse | null>(null);
  const deliveryConfidenceMinimumCoverage = metrics?.ruleset_version === catalog.rulesetVersion
    ? deliveryConfidenceDefinition.availability.minimum_coverage_pct ?? 50
    : 50;
  const [issues, setIssues] = useState<SprintIssue[]>([]);
  const [isLoadingList, setIsLoadingList] = useState(true);
  const [isLoadingDetails, setIsLoadingDetails] = useState(false);
  const [isSprintHealthStatsExpanded, setIsSprintHealthStatsExpanded] = useState(true);
  const [isTicketSituationExpanded, setIsTicketSituationExpanded] = useState(false);
  const [isDeliveryConfidenceExpanded, setIsDeliveryConfidenceExpanded] = useState(true);
  const [isSprintMetricsExpanded, setIsSprintMetricsExpanded] = useState(true);
  const [isSprintChartsExpanded, setIsSprintChartsExpanded] = useState(true);
  const [snapshotBaseline, setSnapshotBaseline] = useState<SnapshotBaseline>("previous");
  const [snapshotComparison, setSnapshotComparison] = useState<SnapshotComparisonResponse | null>(null);
  const [snapshotHistory, setSnapshotHistory] = useState<SnapshotChangeHistoryResponse | null>(null);
  const [isLoadingSnapshotChanges, setIsLoadingSnapshotChanges] = useState(false);
  const [snapshotChangeError, setSnapshotChangeError] = useState<string | null>(null);
  const [sprintChartRows, setSprintChartRows] = useState<SprintChartHistoryPoint[]>([]);
  const [sprintChartRefreshNonce, setSprintChartRefreshNonce] = useState(0);
  const [isLoadingSprintConfidence, setIsLoadingSprintConfidence] = useState(false);
  const [sprintConfidenceError, setSprintConfidenceError] = useState<string | null>(null);

  const issuesByKey = useMemo(() => {
    const map: Record<string, SprintIssue> = {};
    for (const issue of issues) {
      map[issue.issue_key] = issue;
    }
    return map;
  }, [issues]);
  const [isRecomputing, setIsRecomputing] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const scopedCurrentSprint = sprintMatchesProject(currentSprint, activeProjectKey) ? currentSprint : null;
  const scopedClosedSprints = useMemo(
    () => closedSprints.filter((sprint) => sprintMatchesProject(sprint, activeProjectKey)),
    [activeProjectKey, closedSprints]
  );
  const options = useMemo(() => buildOptions(scopedCurrentSprint, scopedClosedSprints), [scopedCurrentSprint, scopedClosedSprints]);
  const selectedScopedSprintId = options.some((option) => option.sprint.sprint_id === selectedSprintId) ? selectedSprintId : null;
  const selectedSprint = options.find((option) => option.sprint.sprint_id === selectedScopedSprintId)?.sprint ?? null;
  const recentSprints = useMemo(() => {
    const sprintsById = new Map<string, Sprint>();
    if (scopedCurrentSprint) {
      sprintsById.set(scopedCurrentSprint.sprint_id, scopedCurrentSprint);
    }
    for (const sprint of scopedClosedSprints) {
      sprintsById.set(sprint.sprint_id, sprint);
    }
    return getRecentSprints(Array.from(sprintsById.values()));
  }, [scopedCurrentSprint, scopedClosedSprints]);
  const sprintConfidenceRows = useMemo<SprintConfidenceRow[]>(
    () =>
      sprintChartRows.map((row) => ({
        sprint_id: row.sprint_id,
        name: row.name,
        delivery_confidence: row.delivery_confidence,
        confidence_delta: row.confidence_delta,
        is_not_closed: row.is_not_closed,
      })),
    [sprintChartRows]
  );
  const sprintCommitmentReliabilityRows = useMemo<SprintCommitmentReliabilityRow[]>(
    () =>
      sprintChartRows.map((row) => ({
        sprint_id: row.sprint_id,
        name: row.name,
        committed_story_points: row.committed_story_points,
        completed_story_points: row.completed_story_points,
        reliability_pct: row.reliability_pct,
        predictability_avg: row.predictability_avg,
        is_not_closed: row.is_not_closed,
      })),
    [sprintChartRows]
  );
  const storyPointUi = buildSprintStoryPointUiVisibility(metrics, deliveryConfidenceMinimumCoverage);
  const storyPointUnavailableReason = getSprintStoryPointUnavailableReason(
    metrics,
    deliveryConfidenceMinimumCoverage,
  );
  const storyPointExplanations = metrics?.delivery_confidence_explanations ?? [];
  const storyPointUnavailableMessage = storyPointExplanations[0] ?? storyPointUnavailableReason;
  const deliveryConfidenceMissingIssueKeys = metrics?.metric_availability?.metrics
    .delivery_confidence_score?.missing_issue_keys ?? [];
  const hasStoryPointMetrics = storyPointUi.hasStoryPointMetrics;
  const predictabilityRows = useMemo(
    () =>
      hasStoryPointMetrics
        ? sprintCommitmentReliabilityRows
        .filter(
          (
            row
          ): row is SprintCommitmentReliabilityRow & {
            committed_story_points: number;
            completed_story_points: number;
          } => row.committed_story_points !== null && row.completed_story_points !== null
        )
        .map((row) => ({
          sprint_id: row.sprint_id,
          name: row.name,
          committed_story_points: row.committed_story_points,
          completed_story_points: row.completed_story_points,
          is_not_closed: row.is_not_closed,
        }))
        : [],
    [hasStoryPointMetrics, sprintCommitmentReliabilityRows]
  );
  const predictabilityCard = useMemo(
    () => (storyPointUi.showTeamPredictability ? buildPredictabilityDisplayModel(predictabilityRows) : null),
    [storyPointUi.showTeamPredictability, predictabilityRows]
  );
  const workDistributionCard = useMemo(
    () => ({
      ...buildWorkDistributionDisplayModel(metrics?.workload_distribution),
      title: metricDefinition(catalog, "sprint", "workload_concentration_pct").label,
    }),
    [catalog, metrics?.workload_distribution]
  );
  const sprintWorkStateCard = useMemo(
    () => (metrics ? buildSprintWorkStateDisplayModel(metrics, issues) : null),
    [metrics, issues]
  );
  const deliveryConfidence = storyPointUi.showPointValues ? metrics?.delivery_confidence ?? null : null;
  const confidenceBreakdown = storyPointUi.showDeliveryConfidenceBreakdown ? metrics?.confidence_breakdown ?? null : null;
  const biggestDeliveryDriver = hasStoryPointMetrics ? metrics?.biggest_driver ?? null : null;
  const scopeCreepCard = useMemo(
    () => (
      metrics?.is_computed
        ? buildScopeCreepDisplayModel(
            metrics,
            catalogMetricStatus(scopeCreepDefinition, metrics.metrics.scope_creep_pct),
          )
        : null
    ),
    [metrics, scopeCreepDefinition]
  );
  const velocityHealthCard = useMemo(
    () => (deliveryConfidence && storyPointUi.showVelocityHealth ? buildVelocityHealthDisplayModel(deliveryConfidence) : null),
    [deliveryConfidence, storyPointUi.showVelocityHealth]
  );
  const metricEvaluations = useMemo(() => {
    if (!metrics) {
      return [];
    }
    const evaluations: MetricEvaluation[] = [];
    if (scopeCreepCard) {
      const value = metrics.metrics.scope_creep_pct;
      evaluations.push({
        key: "scope_creep_pct",
        label: scopeCreepDefinition.label,
        group: "delivery",
        status: scopeCreepCard.status,
        value,
        formattedValue: scopeCreepCard.value,
        focusMessage: `Scope creep is ${scopeCreepCard.status === "critical" ? "critical" : "at watch level"} at ${scopeCreepCard.value}.`,
      });
    }
    if (velocityHealthCard) {
      const average = deliveryConfidence?.inputs.historical_velocity;
      const completed = deliveryConfidence?.inputs.completed_effective_points;
      const value = average && average > 0 && completed !== undefined ? Number(((completed / average) * 100).toFixed(0)) : null;
      evaluations.push({
        key: "velocity_health",
        label: "Velocity health",
        group: "delivery",
        status: velocityHealthCard.status,
        value,
        formattedValue: velocityHealthCard.value,
        focusMessage: value === null ? "Velocity health needs more closed sprint data." : `Velocity health is only ${velocityHealthCard.value} of normal.`,
      });
    }
    evaluations.push(buildBaseMetricEvaluation("open_high_severity_bugs", metrics, metricDefinition(catalog, "sprint", "open_high_severity_bugs")));
    evaluations.push(buildBaseMetricEvaluation("completed_scope_pct", metrics, metricDefinition(catalog, "sprint", "completed_scope_pct")));
    evaluations.push(buildBaseMetricEvaluation("open_blockers", metrics, metricDefinition(catalog, "sprint", "open_blockers")));
    evaluations.push(buildBaseMetricEvaluation("rollover_count", metrics, metricDefinition(catalog, "sprint", "rollover_count")));
    evaluations.push(buildBaseMetricEvaluation("reopen_rate_pct", metrics, metricDefinition(catalog, "sprint", "reopen_rate_pct")));
    evaluations.push(buildBaseMetricEvaluation("median_cycle_time_days", metrics, metricDefinition(catalog, "sprint", "median_cycle_time_days")));
    evaluations.push(buildBaseMetricEvaluation("bugs_created_during_sprint", metrics, metricDefinition(catalog, "sprint", "bugs_created_during_sprint")));
    if (workDistributionCard) {
      evaluations.push({
        key: "work_distribution",
        label: metricDefinition(catalog, "sprint", "workload_concentration_pct").label,
        group: "risk",
        status: workDistributionCard.status,
        value: Number.parseFloat(workDistributionCard.value),
        formattedValue: workDistributionCard.value,
        focusMessage: `Workload concentration is ${workDistributionCard.value} for the top assignee.`,
      });
    }
    if (predictabilityCard) {
      evaluations.push({
        key: "team_predictability",
        label: "Team predictability",
        group: "delivery",
        status: predictabilityCard.status,
        value: Number.parseFloat(predictabilityCard.value),
        formattedValue: predictabilityCard.value,
        focusMessage: `Team predictability is ${predictabilityCard.value}.`,
      });
    }
    return evaluations;
  }, [catalog, deliveryConfidence, metrics, predictabilityCard, scopeCreepCard, scopeCreepDefinition, velocityHealthCard, workDistributionCard]);
  const focusAreas = useMemo(() => generateFocusAreas(metricEvaluations), [metricEvaluations]);
  const riskHeatmapCells = useMemo(() => buildRiskHeatmapRows(sprintChartRows), [sprintChartRows]);
  const latestConfidenceDelta = sprintConfidenceRows.length > 1
    ? sprintConfidenceRows[sprintConfidenceRows.length - 1].confidence_delta
    : null;
  const hasConfidenceTrend = storyPointUi.showDeliveryConfidenceTrend && hasChartData(sprintChartRows, ["delivery_confidence"]);
  const hasConfidenceBreakdown = storyPointUi.showDeliveryConfidenceBreakdown && hasChartData(sprintChartRows, [
    "progress_alignment",
    "velocity_fit",
    "scope_stability",
    "blocker_health",
  ]);
  const hasCommitmentTrend = storyPointUi.showCommitmentReliability && hasChartData(sprintCommitmentReliabilityRows, [
    "committed_story_points",
    "completed_story_points",
  ]);
  const hasReliabilityTrend = storyPointUi.showCommitmentReliability && hasChartData(sprintCommitmentReliabilityRows, ["reliability_pct"]);
  const hasPredictabilityTrend = storyPointUi.showTeamPredictability && sprintCommitmentReliabilityRows.some((row) => row.predictability_avg !== null);
  const hasScopeTrend = hasChartData(sprintChartRows, ["scope_change_count", "scope_creep_pct"]);
  const hasQualityCountTrend = hasChartData(sprintChartRows, [
    "open_high_severity_bugs",
    "bugs_created_during_sprint",
  ]);
  const hasReopenTrend = hasChartData(sprintChartRows, ["reopen_rate_pct"]);
  const hasFlowTrend = hasChartData(sprintChartRows, ["median_cycle_time_days"]);

  useEffect(() => {
    setCurrentSprint(null);
    setClosedSprints([]);
    setSelectedSprintId(null);
    setMetrics(null);
    setIssues([]);
    setSnapshotComparison(null);
    setSnapshotHistory(null);
    setSnapshotChangeError(null);
    setSprintChartRows([]);
    setSprintConfidenceError(null);
    setIsLoadingDetails(false);
    setIsLoadingSnapshotChanges(false);
    setIsLoadingSprintConfidence(false);
  }, [activeProjectKey]);

  useEffect(() => {
    let isActive = true;

    async function loadSprintList() {
      if (!activeProjectKey) {
        setCurrentSprint(null);
        setClosedSprints([]);
        setSelectedSprintId(null);
        setIsLoadingList(false);
        return;
      }

      setIsLoadingList(true);
      setErrorMessage(null);
      setCurrentSprint(null);
      setClosedSprints([]);
      setSelectedSprintId(null);
      try {
        const [currentResult, closedResult] = await Promise.allSettled([
          apiClient.getCurrentSprint(activeProjectKey),
          apiClient.getClosedSprints(activeProjectKey),
        ]);
        if (!isActive) {
          return;
        }
        const activeSprint = currentResult.status === "fulfilled" && sprintMatchesProject(currentResult.value.item, activeProjectKey)
          ? currentResult.value.item
          : null;
        const closed = closedResult.status === "fulfilled"
          ? closedResult.value.items.filter((sprint) => sprintMatchesProject(sprint, activeProjectKey))
          : [];
        setCurrentSprint(activeSprint);
        setClosedSprints(closed);
        setSelectedSprintId(activeSprint?.sprint_id ?? closed[0]?.sprint_id ?? null);
        const failures = [currentResult, closedResult]
          .filter((result): result is PromiseRejectedResult => result.status === "rejected")
          .map((result) => result.reason instanceof Error ? result.reason.message : "Failed to load sprints.");
        if (failures.length > 0) {
          setErrorMessage(failures.join(" "));
        }
      } finally {
        if (isActive) {
          setIsLoadingList(false);
        }
      }
    }

    void loadSprintList();

    return () => {
      isActive = false;
    };
  }, [activeProjectKey, refreshNonce]);

  useEffect(() => {
    if (!selectedScopedSprintId) {
      setMetrics(null);
      setIssues([]);
      return;
    }

    const sprintId = selectedScopedSprintId;
    let isActive = true;

    async function loadSprintDetails() {
      setIsLoadingDetails(true);
      setErrorMessage(null);
      setMetrics(null);
      setIssues([]);
      try {
        const [metricsResponse, issueResponse] = await Promise.all([
          apiClient.getSprintMetrics(sprintId),
          loadAllSprintIssues(sprintId),
        ]);
        if (!isActive) {
          return;
        }
        setMetrics(metricsResponse);
        setIssues(issueResponse);
      } catch (error) {
        if (isActive) {
          setMetrics(null);
          setIssues([]);
          setErrorMessage(error instanceof Error ? error.message : "Failed to load sprint details.");
        }
      } finally {
        if (isActive) {
          setIsLoadingDetails(false);
        }
      }
    }

    void loadSprintDetails();

    return () => {
      isActive = false;
    };
  }, [selectedScopedSprintId]);

  useEffect(() => {
    if (mode !== "reports" || !selectedScopedSprintId) {
      setSnapshotComparison(null);
      setSnapshotHistory(null);
      return;
    }

    const sprintId = selectedScopedSprintId;
    let isActive = true;

    async function loadSnapshotChanges() {
      setIsLoadingSnapshotChanges(true);
      setSnapshotChangeError(null);
      setSnapshotComparison(null);
      setSnapshotHistory(null);
      try {
        const [comparison, history] = await Promise.all([
          apiClient.getSprintSnapshotComparison(sprintId, snapshotBaseline),
          apiClient.getSprintSnapshotChangeHistory(sprintId),
        ]);
        if (isActive) {
          setSnapshotComparison(comparison);
          setSnapshotHistory(history);
        }
      } catch (error) {
        if (isActive) {
          setSnapshotChangeError(error instanceof Error ? error.message : "Failed to load snapshot changes.");
          setSnapshotComparison(null);
          setSnapshotHistory(null);
        }
      } finally {
        if (isActive) {
          setIsLoadingSnapshotChanges(false);
        }
      }
    }

    void loadSnapshotChanges();

    return () => {
      isActive = false;
    };
  }, [mode, selectedScopedSprintId, snapshotBaseline, refreshNonce, sprintChartRefreshNonce]);

  useEffect(() => {
    if (recentSprints.length === 0) {
      setSprintChartRows([]);
      return;
    }

    let isActive = true;

    async function loadSprintConfidence() {
      setIsLoadingSprintConfidence(true);
      setSprintConfidenceError(null);
      setSprintChartRows([]);
      try {
        const sources = await Promise.all(
          recentSprints.map(async (sprint) => {
            const response = await apiClient.getSprintMetrics(sprint.sprint_id);
            return {
              sprint_id: sprint.sprint_id,
              name: sprint.name,
              is_not_closed: isNotClosedSprint(sprint),
              metrics: response,
              scope_creep_definition: scopeCreepDefinition,
            };
          })
        );

        if (isActive) {
          setSprintChartRows(buildSprintChartHistory(sources));
        }
      } catch (error) {
        if (isActive) {
          setSprintChartRows([]);
          setSprintConfidenceError(error instanceof Error ? error.message : "Failed to load sprint confidence.");
        }
      } finally {
        if (isActive) {
          setIsLoadingSprintConfidence(false);
        }
      }
    }

    void loadSprintConfidence();

    return () => {
      isActive = false;
    };
  }, [recentSprints, refreshNonce, scopeCreepDefinition, sprintChartRefreshNonce]);

  async function handleRecomputeSprint() {
    if (!selectedScopedSprintId || isRecomputing) {
      return;
    }
    setIsRecomputing(true);
    setErrorMessage(null);
    try {
      await apiClient.recomputeSprint(selectedScopedSprintId);
      const [metricsResponse, issueResponse] = await Promise.all([
        apiClient.getSprintMetrics(selectedScopedSprintId),
        loadAllSprintIssues(selectedScopedSprintId),
      ]);
      setMetrics(metricsResponse);
      setIssues(issueResponse);
      setSprintChartRefreshNonce((current) => current + 1);
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : "Failed to recompute sprint metrics.");
    } finally {
      setIsRecomputing(false);
    }
  }

  return (
    <div className="sprints-panel">
      {errorMessage ? <div className="panel error-panel" role="alert">{errorMessage}</div> : null}

      {mode === "intelligence" ? (
        <>
          <SprintReportExportPanel
            sprintId={selectedScopedSprintId}
            sprintName={selectedSprint?.name ?? null}
          />
          <SprintDeliveryConfidencePanel
            metrics={metrics}
            deliveryConfidence={deliveryConfidence}
            confidenceBreakdown={confidenceBreakdown}
            biggestDeliveryDriver={biggestDeliveryDriver}
            storyPointExplanations={storyPointExplanations}
            missingIssueKeys={deliveryConfidenceMissingIssueKeys}
            showUnavailableMessage={storyPointUi.showStoryPointUnavailableMessage}
            isLoading={isLoadingDetails}
            isExpanded={isDeliveryConfidenceExpanded}
            onToggle={() => setIsDeliveryConfidenceExpanded((current) => !current)}
          />
          <SprintMetricsPanel
            metrics={metrics}
            deliveryConfidence={deliveryConfidence}
            issuesByKey={issuesByKey}
            metricEvaluations={metricEvaluations}
            focusAreas={focusAreas}
            scopeCreepCard={scopeCreepCard}
            velocityHealthCard={velocityHealthCard}
            predictabilityCard={predictabilityCard}
            workDistributionCard={workDistributionCard}
            sprintWorkStateCard={sprintWorkStateCard}
            isLoading={isLoadingDetails}
            isExpanded={isSprintMetricsExpanded}
            onToggle={() => setIsSprintMetricsExpanded((current) => !current)}
            onSelectIssue={onSelectIssue}
          />
          <SprintHealthPanel
            isExpanded={isSprintHealthStatsExpanded}
            options={options}
            selectedSprintId={selectedScopedSprintId}
            selectedSprint={selectedSprint}
            isLoadingList={isLoadingList}
            isRecomputing={isRecomputing}
            snapshotAgeHours={metrics?.snapshot_age_hours ?? null}
            onToggle={() => setIsSprintHealthStatsExpanded((current) => !current)}
            onSelectSprint={setSelectedSprintId}
            onRecompute={() => void handleRecomputeSprint()}
          />
          <SprintTicketSituationPanel
            isExpanded={isTicketSituationExpanded}
            selectedSprintId={selectedScopedSprintId}
            isLoadingDetails={isLoadingDetails}
            issues={issues}
            onToggle={() => setIsTicketSituationExpanded((current) => !current)}
            onSelectIssue={onSelectIssue}
          />
        </>
      ) : null}

      {mode === "reports" ? (
        <SprintReportsPanel
          isExpanded={isSprintChartsExpanded}
          storyPointUi={storyPointUi}
          storyPointUnavailableMessage={storyPointUnavailableMessage}
          snapshotComparison={snapshotComparison}
          snapshotHistory={snapshotHistory}
          snapshotBaseline={snapshotBaseline}
          isLoadingSnapshotChanges={isLoadingSnapshotChanges}
          snapshotChangeError={snapshotChangeError}
          biggestDeliveryDriver={biggestDeliveryDriver}
          sprintConfidenceRows={sprintConfidenceRows}
          sprintCommitmentReliabilityRows={sprintCommitmentReliabilityRows}
          sprintChartRows={sprintChartRows}
          riskHeatmapCells={riskHeatmapCells}
          latestConfidenceDelta={latestConfidenceDelta}
          isLoadingSprintConfidence={isLoadingSprintConfidence}
          sprintConfidenceError={sprintConfidenceError}
          hasConfidenceTrend={hasConfidenceTrend}
          hasConfidenceBreakdown={hasConfidenceBreakdown}
          hasCommitmentTrend={hasCommitmentTrend}
          hasReliabilityTrend={hasReliabilityTrend}
          hasPredictabilityTrend={hasPredictabilityTrend}
          hasScopeTrend={hasScopeTrend}
          hasQualityCountTrend={hasQualityCountTrend}
          hasReopenTrend={hasReopenTrend}
          hasFlowTrend={hasFlowTrend}
          onToggle={() => setIsSprintChartsExpanded((current) => !current)}
          onBaselineChange={setSnapshotBaseline}
        />
      ) : null}
    </div>
  );
}
