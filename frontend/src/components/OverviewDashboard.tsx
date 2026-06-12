import type { CSSProperties } from "react";
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
} from "../api/types";
import { RecommendationsPanel } from "./RecommendationsPanel";

interface OverviewDashboardProps {
  release: Release | null;
  metrics: ReleaseMetricsResponse | null;
  charts: ReleaseChartsResponse | null;
  signal: ReleaseSignalResponse | null;
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
  reopen_rate_pct: "Reopen Rate",
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
      label: formatDateLabel(point.snapshot_at),
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

function getPredictedConfidence(charts: ReleaseChartsResponse | null, release: Release | null) {
  const rows = buildConfidenceTrendRows(charts);
  if (rows.length === 0) {
    return null;
  }
  const latest = rows[rows.length - 1];
  if (rows.length < 2 || !release?.release_date) {
    return latest.value;
  }

  const first = rows[0];
  const firstTime = Date.parse(first.timestamp);
  const latestTime = Date.parse(latest.timestamp);
  const releaseTime = Date.parse(release.release_date);
  if (!Number.isFinite(firstTime) || !Number.isFinite(latestTime) || !Number.isFinite(releaseTime)) {
    return latest.value;
  }
  if (latestTime <= firstTime || releaseTime <= latestTime) {
    return latest.value;
  }

  const slopePerMs = (latest.value - first.value) / (latestTime - firstTime);
  return clampPercentage(latest.value + slopePerMs * (releaseTime - latestTime));
}

function getReadinessBasis(charts: ReleaseChartsResponse | null, signal: ReleaseSignalResponse | null) {
  const readiness = latestValue(charts?.series.readiness_pct);
  if (readiness !== null) {
    return readiness;
  }
  if (signal && signal.release_gates.length > 0) {
    const passed = signal.release_gates.filter((gate) => gate.passed).length;
    return (passed / signal.release_gates.length) * 100;
  }
  return null;
}

function getTargetChance(charts: ReleaseChartsResponse | null, signal: ReleaseSignalResponse | null, release: Release | null) {
  const predicted = getPredictedConfidence(charts, release);
  const readiness = getReadinessBasis(charts, signal);
  if (predicted === null || readiness === null) {
    return null;
  }
  return clampPercentage((predicted * readiness) / 100);
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

export function OverviewDashboard({
  release,
  metrics,
  charts,
  signal,
  isLoading,
  onOpenReports,
}: OverviewDashboardProps) {
  const confidenceScore = getConfidenceScore(signal, charts);
  const tone = getSignalTone(signal);
  const riskDrivers = getRiskDrivers(signal);
  const trendRows = buildConfidenceTrendRows(charts);
  const delta = getConfidenceDelta(charts);
  const predictedConfidence = getPredictedConfidence(charts, release);
  const targetChance = getTargetChance(charts, signal, release);
  const summary = signal?.summary ?? "Signal data has not been computed for this release yet.";
  const warnings = signal?.warnings ?? [];
  const blockers = getMetricValue(metrics, "open_blockers");
  const bugs = getMetricValue(metrics, "open_high_severity_bugs");

  if (isLoading) {
    return <section className="overview-loading panel">Loading release intelligence...</section>;
  }

  return (
    <>
      <section className="overview-card readiness-card">
        <p className="overview-card-kicker">Release Readiness</p>
        <strong className={`readiness-score readiness-${tone}`}>{formatPercentage(confidenceScore)}</strong>
        <span className="readiness-label">Confidence</span>
        <span className={`readiness-pill readiness-${tone}`}>{getStatusLabel(signal)}</span>
        <p className="overview-copy">{summary}</p>
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
            <p className="muted">No confidence history available yet.</p>
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

      <section className="overview-card prediction-card">
        <p className="overview-card-kicker">Release Prediction</p>
        <p className="overview-copy">If current trends continue</p>
        <strong>{formatPercentage(targetChance)}</strong>
        <span>chance of meeting release targets</span>
        <p className="overview-copy">Predicted confidence at release: {formatPercentage(predictedConfidence)}</p>
        <button type="button" className="overview-link-button" onClick={onOpenReports}>
          View prediction factors
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
        <p className="overview-footnote">Aging risks increase the likelihood of release failure.</p>
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
    </>
  );
}
