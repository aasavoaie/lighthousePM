import { useEffect, useState, type CSSProperties } from "react";
import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import type {
  ChartPoint,
  MetricValues,
  Release,
  ReleaseChartsResponse,
  ReleaseMetricsResponse,
  ReleaseSignalResponse,
  SignalRiskAgingGroup,
  SignalRiskItem,
  Sprint,
  SprintMetricsResponse,
} from "../api/types";
import { apiClient } from "../api/client";
import { RecommendationsPanel } from "./RecommendationsPanel";
import { getReleaseScoreDisplay } from "./releaseAvailability";

interface OverviewDashboardProps {
  projectKey: string | null;
  release: Release | null;
  metrics: ReleaseMetricsResponse | null;
  charts: ReleaseChartsResponse | null;
  signal: ReleaseSignalResponse | null;
  refreshNonce: number;
  isLoading: boolean;
  onOpenReports: () => void;
  onOpenReleaseMetric: (metricName: keyof MetricValues) => void;
}

type RiskDriver = {
  metricName: string;
  label: string;
  level: string;
  contributionPct: number;
};

const riskLabels: Record<string, string> = {
  open_blockers: "Open Blockers",
  open_high_severity_bugs: "High Severity Bugs",
  scope_churn_7d_pct: "Scope Churn",
  reopen_rate_pct: "Reopen Events / 100 Eligible Tickets",
  median_cycle_time_days: "Cycle Time",
};

function clampPercentage(value: number) {
  return Math.max(0, Math.min(100, value));
}

function formatPercentage(value: number | null | undefined) {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return "N/A";
  }
  return `${Math.round(value)}%`;
}

function latestValue(points: ChartPoint[] | undefined) {
  const numericPoints = (points ?? []).filter((point) => point.value !== null);
  return numericPoints.length > 0 ? (numericPoints[numericPoints.length - 1].value as number) : null;
}

function formatDateLabel(value: string) {
  return new Date(value).toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

function buildConfidenceTrendRows(charts: ReleaseChartsResponse | null) {
  return (charts?.series.confidence_score ?? [])
    .filter((point) => point.value !== null)
    .map((point) => ({
      label: `${formatDateLabel(point.snapshot_at)}${point.version_boundary ? ` · v${point.ruleset_version}` : ""}`,
      timestamp: point.snapshot_at,
      value: point.value as number,
    }));
}

function getConfidenceDelta(charts: ReleaseChartsResponse | null) {
  const rows = buildConfidenceTrendRows(charts);
  if (rows.length < 2) {
    return null;
  }
  return rows[rows.length - 1].value - rows[0].value;
}

function getRiskDrivers(signal: ReleaseSignalResponse | null): RiskDriver[] {
  if (!signal) {
    return [];
  }

  const rowsByMetric = new Map<string, RiskDriver>();
  for (const item of [...signal.critical_risks, ...signal.warnings]) {
    const existing = rowsByMetric.get(item.metric_name);
    if (!existing || item.contribution_pct > existing.contributionPct) {
      rowsByMetric.set(item.metric_name, {
        metricName: item.metric_name,
        label: riskLabels[item.metric_name] ?? item.metric_name,
        level: item.level,
        contributionPct: item.contribution_pct,
      });
    }
  }

  return Array.from(rowsByMetric.values())
    .filter((row) => row.contributionPct > 0)
    .sort((left, right) => right.contributionPct - left.contributionPct)
    .slice(0, 5);
}

function getConfidenceScore(signal: ReleaseSignalResponse | null, charts: ReleaseChartsResponse | null) {
  return signal?.confidence_score ?? latestValue(charts?.series.confidence_score);
}

function getStatusLabel(signal: ReleaseSignalResponse | null) {
  if (signal?.status_label) {
    return signal.status_label;
  }
  if (signal?.signal === "GREEN") {
    return "READY FOR RELEASE";
  }
  if (signal?.signal === "YELLOW") {
    return "NEEDS ATTENTION";
  }
  if (signal?.signal === "RED") {
    return "NOT READY FOR RELEASE";
  }
  return "NOT COMPUTED";
}

function getSignalTone(signal: ReleaseSignalResponse | null) {
  if (signal?.signal === "GREEN") {
    return "good";
  }
  if (signal?.signal === "YELLOW") {
    return "warning";
  }
  if (signal?.signal === "RED") {
    return "critical";
  }
  return "neutral";
}

function formatOutlookDays(daysRemaining: number | null) {
  if (daysRemaining === null) {
    return "Release date timing unavailable";
  }
  if (daysRemaining === 0) {
    return "Jira release date is today";
  }
  return daysRemaining > 0
    ? `${daysRemaining} calendar days remaining`
    : `${Math.abs(daysRemaining)} calendar days past the Jira release date`;
}

function formatOutlookConfidenceChange(change: number | null, hasBaseline: boolean) {
  if (!hasBaseline || change === null) {
    return "24-hour confidence baseline unavailable";
  }
  const prefix = change > 0 ? "+" : "";
  return `${prefix}${change.toFixed(1)} confidence points against the 24-hour baseline`;
}

function getMetricValue(metrics: ReleaseMetricsResponse | null, metricName: keyof MetricValues) {
  return metrics?.metrics[metricName] ?? null;
}

function getRiskAgingPercent(group: SignalRiskAgingGroup) {
  if (group.count === 0) {
    return 0;
  }
  const oldest = group.oldest_age_days ?? 0;
  return clampPercentage(Math.max(group.count * 12, oldest * 1.8));
}

function renderAgingCard(title: string, group: SignalRiskAgingGroup, noun: string) {
  return (
    <article className={`overview-aging-card ${group.count === 0 ? "is-zero" : ""}`}>
      <div>
        <strong>{group.count}</strong>
        <span>{noun}</span>
      </div>
      <p>{title}</p>
      <small>
        Oldest: {group.oldest_age_days?.toFixed(1) ?? "N/A"} days
        <br />
        Average: {group.average_age_days?.toFixed(1) ?? "N/A"} days
        {group.unknown_count > 0 ? <><br />Unavailable: {group.unknown_count}</> : null}
      </small>
      <span
        className="overview-aging-meter"
        style={{ "--aging-width": `${getRiskAgingPercent(group)}%` } as CSSProperties}
        aria-hidden="true"
      />
    </article>
  );
}

function renderWarning(item: SignalRiskItem) {
  return (
    <li key={`${item.level}-${item.metric_name}-${item.message}`}>
      <span className="overview-warning-dot" aria-hidden="true" />
      <span>{item.message}</span>
    </li>
  );
}

function formatDate(value: string | null) {
  if (!value) {
    return "N/A";
  }
  return new Date(value).toLocaleDateString();
}

function sprintSnapshotStatus(sprint: Sprint | null, metrics: SprintMetricsResponse | null) {
  if (!sprint) {
    return "No sprint snapshot available yet.";
  }
  if (!metrics?.is_computed) {
    return "No sprint snapshot available yet.";
  }
  return metrics.snapshot_at ? `Latest snapshot ${new Date(metrics.snapshot_at).toLocaleString()}` : "No sprint snapshot available yet.";
}

export function OverviewDashboard({
  projectKey,
  metrics,
  charts,
  signal,
  refreshNonce,
  isLoading,
  onOpenReports,
}: OverviewDashboardProps) {
  const [currentSprint, setCurrentSprint] = useState<Sprint | null>(null);
  const [currentSprintMetrics, setCurrentSprintMetrics] = useState<SprintMetricsResponse | null>(null);
  const [isLoadingSprint, setIsLoadingSprint] = useState(false);
  const [sprintError, setSprintError] = useState<string | null>(null);
  const confidenceScore = getConfidenceScore(signal, charts);
  const scoreDisplay = getReleaseScoreDisplay(metrics);
  const tone = getSignalTone(signal);
  const riskDrivers = getRiskDrivers(signal);
  const trendRows = buildConfidenceTrendRows(charts);
  const delta = getConfidenceDelta(charts);
  const outlook = signal?.release_outlook ?? null;
  const hasReleaseSnapshot = metrics?.is_computed === true;
  const summary = hasReleaseSnapshot
    ? signal?.summary ?? "Signal data has not been computed for this release yet."
    : "No snapshot available yet.";
  const readinessSummary = scoreDisplay.isAvailable ? summary : scoreDisplay.reason;
  const warnings = signal?.warnings ?? [];
  const blockers = getMetricValue(metrics, "open_blockers");
  const bugs = getMetricValue(metrics, "open_high_severity_bugs");

  useEffect(() => {
    if (!projectKey) {
      setCurrentSprint(null);
      setCurrentSprintMetrics(null);
      setSprintError(null);
      setIsLoadingSprint(false);
      return;
    }

    let isActive = true;

    async function loadCurrentSprint() {
      setCurrentSprint(null);
      setCurrentSprintMetrics(null);
      setIsLoadingSprint(true);
      setSprintError(null);
      try {
        const response = await apiClient.getCurrentSprint(projectKey);
        if (!isActive) {
          return;
        }
        setCurrentSprint(response.item);
        if (!response.item) {
          setCurrentSprintMetrics(null);
          return;
        }
        const metricsResponse = await apiClient.getSprintMetrics(response.item.sprint_id);
        if (isActive) {
          setCurrentSprintMetrics(metricsResponse);
        }
      } catch (error) {
        if (isActive) {
          setCurrentSprint(null);
          setCurrentSprintMetrics(null);
          setSprintError(error instanceof Error ? error.message : "Failed to load active sprint.");
        }
      } finally {
        if (isActive) {
          setIsLoadingSprint(false);
        }
      }
    }

    void loadCurrentSprint();

    return () => {
      isActive = false;
    };
  }, [projectKey, refreshNonce]);

  if (isLoading) {
    return <section className="overview-loading panel">Loading release intelligence...</section>;
  }

  return (
    <>
      <section className="overview-card readiness-card">
        <p className="overview-card-kicker">Release Readiness</p>
        <strong className={`readiness-score readiness-${scoreDisplay.isAvailable ? tone : "neutral"} ${scoreDisplay.isAvailable ? "" : "readiness-score-unavailable"}`}>
          {scoreDisplay.value ?? formatPercentage(confidenceScore)}
        </strong>
        <span className="readiness-label">{scoreDisplay.label}</span>
        <span className={`readiness-pill readiness-${tone}`}>{getStatusLabel(signal)}</span>
        <p className="overview-copy">{readinessSummary}</p>
      </section>

      <section className="overview-card confidence-engine-card">
        <p className="overview-card-kicker">Confidence Engine</p>
        <h2>What's hurting confidence?</h2>
        <div className="risk-driver-list">
          {riskDrivers.length > 0 ? (
            riskDrivers.map((driver) => (
              <div className="risk-driver-row" key={driver.metricName}>
                <span className={`risk-driver-icon risk-${driver.level.toLowerCase()}`} aria-hidden="true" />
                <span>{driver.label}</span>
                <span
                  className="risk-driver-meter"
                  style={{ "--driver-width": `${clampPercentage(driver.contributionPct)}%` } as CSSProperties}
                  aria-hidden="true"
                />
              </div>
            ))
          ) : (
            <p className="muted">No active confidence reducers.</p>
          )}
        </div>
        <p className="overview-copy">These factors are reducing your confidence score.</p>
      </section>

      <section className="overview-card trend-card">
        <div className="trend-card-header">
          <p className="overview-card-kicker">Confidence Trend</p>
          {confidenceScore !== null && confidenceScore !== undefined ? (
            <span className="trend-current-label">{formatPercentage(confidenceScore)}</span>
          ) : null}
        </div>
        <div className="overview-trend-chart">
          {trendRows.length > 0 ? (
            <ResponsiveContainer width="100%" height={220}>
              <LineChart data={trendRows} margin={{ top: 18, right: 20, bottom: 6, left: -12 }}>
                <CartesianGrid vertical={false} stroke="#eceef6" />
                <XAxis dataKey="label" tickLine={false} axisLine={false} tick={{ fill: "#3f4d71", fontSize: 12 }} />
                <YAxis
                  domain={[0, 100]}
                  ticks={[0, 25, 50, 75, 100]}
                  tickFormatter={(value) => `${value}%`}
                  tickLine={false}
                  axisLine={false}
                  tick={{ fill: "#3f4d71", fontSize: 12 }}
                />
                <Tooltip formatter={(value) => [`${Math.round(Number(value))}%`, "Confidence"]} />
                <Line
                  type="monotone"
                  dataKey="value"
                  stroke="#4b22d4"
                  strokeWidth={3}
                  dot={{ r: 4, fill: "#ffffff", stroke: "#4b22d4", strokeWidth: 2 }}
                  activeDot={{ r: 5 }}
                />
              </LineChart>
            </ResponsiveContainer>
          ) : (
            <p className="muted">No snapshot available yet.</p>
          )}
        </div>
        {delta !== null ? (
          <p className={`trend-delta ${delta < 0 ? "negative" : "positive"}`}>
            {Math.abs(Math.round(delta))}% {delta < 0 ? "decrease" : "increase"} since first snapshot
          </p>
        ) : (
          <p className="muted">Trend baseline unavailable.</p>
        )}
      </section>

      <section className="overview-card outlook-card">
        <p className="overview-card-kicker">Release Outlook</p>
        <strong>{outlook?.label ?? "NOT COMPUTED"}</strong>
        <span>Current confidence: {formatPercentage(outlook?.confidence_score)}</span>
        <p className="overview-copy">{formatOutlookDays(outlook?.days_remaining ?? null)}</p>
        <p className="overview-copy">
          {outlook ? `${outlook.passed_gate_count} passed / ${outlook.failed_gate_count} failed release gates` : "Release gates unavailable"}
        </p>
        <p className="overview-copy">
          {formatOutlookConfidenceChange(
            outlook?.confidence_change_24h ?? null,
            outlook?.confidence_baseline_at !== null && outlook?.confidence_baseline_at !== undefined
          )}
        </p>
        <p className="overview-copy">
          {outlook ? `${outlook.active_conditions.length} active RED/YELLOW conditions` : "Active conditions unavailable"}
        </p>
        <p className="overview-footnote">
          {outlook?.disclaimer ?? "This outlook reflects the latest stored snapshot and is not a forecast."}
        </p>
        <button type="button" className="overview-link-button" onClick={onOpenReports}>
          View outlook evidence
        </button>
      </section>

      <section className="overview-card risk-aging-card">
        <p className="overview-card-kicker">Risk Aging</p>
        <div className="overview-aging-grid">
          {signal
            ? renderAgingCard(
                `${blockers ?? signal.risk_aging.blockers.count} blockers remain open`,
                signal.risk_aging.blockers,
                "blockers remain open"
              )
            : null}
          {signal
            ? renderAgingCard(
                `${bugs ?? signal.risk_aging.high_severity_bugs.count} high severity bugs remain unresolved`,
                signal.risk_aging.high_severity_bugs,
                "high severity bugs remain unresolved"
              )
            : null}
        </div>
        {!signal ? <p className="muted">No aging data available.</p> : null}
        <p className="overview-footnote">Older unresolved risks require attention before release.</p>
      </section>

      <section className="overview-card actions-card">
        <RecommendationsPanel recommendations={metrics?.recommendations ?? []} />
        <p className="overview-footnote">Actions are prioritized by confidence impact.</p>
      </section>

      <section className="overview-card warnings-card">
        <p className="overview-card-kicker">Additional Warnings</p>
        {warnings.length > 0 ? (
          <ul>{warnings.map(renderWarning)}</ul>
        ) : (
          <p className="muted">No additional warnings.</p>
        )}
        <p className="overview-footnote">Addressing these warnings will improve stability.</p>
      </section>

      <section className="overview-card active-sprint-card">
        <p className="overview-card-kicker">Active Sprint</p>
        {isLoadingSprint ? <p className="muted">Loading active sprint...</p> : null}
        {sprintError ? <p className="error-text">{sprintError}</p> : null}
        {!isLoadingSprint && !sprintError ? (
          <>
            <h2>{currentSprint?.name ?? "No active sprint"}</h2>
            <p className="overview-copy">{sprintSnapshotStatus(currentSprint, currentSprintMetrics)}</p>
            {currentSprint ? (
              <dl className="confidence-inputs">
                <dt>Project</dt>
                <dd>{currentSprint.project_key}</dd>
                <dt>State</dt>
                <dd>{currentSprint.state}</dd>
                <dt>End</dt>
                <dd>{formatDate(currentSprint.end_date)}</dd>
                <dt>Delivery confidence</dt>
                <dd>{formatPercentage(currentSprintMetrics?.metrics.delivery_confidence_score)}</dd>
              </dl>
            ) : null}
          </>
        ) : null}
      </section>
    </>
  );
}
