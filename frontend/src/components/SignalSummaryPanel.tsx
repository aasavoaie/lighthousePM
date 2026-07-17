import { useEffect, useMemo, useState } from "react";

import { apiClient } from "../api/client";
import type {
  Issue,
  Release,
  ReleaseSignalResponse,
  SignalGate,
  SignalLast24HoursItem,
  SignalRiskAgingGroup,
  SignalRiskItem,
} from "../api/types";
import { BiggestDriverCard } from "./BiggestDriverCard";
import { ConfidenceBreakdownCard } from "./ConfidenceBreakdownCard";
import { getRecentProjectReleases } from "../releaseScope";

interface SignalSummaryPanelProps {
  signal: ReleaseSignalResponse | null;
  isLoading: boolean;
  releases: Release[];
  selectedProjectKey: string | null;
  refreshNonce: number;
}

type SignalTrend = "increasing" | "decreasing" | "similar";

type ReleaseSignalTrendRow = {
  release_id: string;
  signal: string;
};

function signalClassName(signalValue: string | null) {
  if (signalValue === "RED") {
    return "signal-badge signal-red";
  }
  if (signalValue === "YELLOW") {
    return "signal-badge signal-yellow";
  }
  if (signalValue === "GREEN") {
    return "signal-badge signal-green";
  }
  return "signal-badge signal-unknown";
}

function signalDescription(signalValue: string | null) {
  if (signalValue === "RED") {
    return "Current release confidence is in the red band.";
  }
  if (signalValue === "YELLOW") {
    return "Current release confidence is in the yellow band.";
  }
  if (signalValue === "GREEN") {
    return "Current release confidence is in the green band.";
  }
  return "Signal not computed yet for this release snapshot.";
}

function signalStatusLabel(signalValue: ReleaseSignalResponse | null) {
  if (signalValue?.status_label) {
    return signalValue.status_label;
  }
  if (signalValue?.signal === "RED") {
    return "NOT READY FOR RELEASE";
  }
  if (signalValue?.signal === "YELLOW") {
    return "RELEASE NEEDS ATTENTION";
  }
  if (signalValue?.signal === "GREEN") {
    return "READY FOR RELEASE";
  }
  return "NOT COMPUTED";
}

function renderReleaseGate(gate: SignalGate) {
  return (
    <li className={gate.passed ? "signal-gate-pass" : "signal-gate-fail"} key={gate.metric_name}>
      <span className="signal-gate-state">{gate.passed ? "PASS" : "FAIL"}</span>
      <span>{gate.label}</span>
    </li>
  );
}

function renderRiskItem(item: SignalRiskItem) {
  return (
    <li className={`signal-risk-item ${item.level.toLowerCase()}`} key={`${item.level}-${item.metric_name}`}>
      <span className="signal-risk-dot" aria-hidden="true" />
      <span>{item.message}</span>
    </li>
  );
}

function formatAgeDays(value: number | null) {
  if (value === null) {
    return "N/A";
  }
  const formatted = Number.isInteger(value) ? value.toFixed(0) : value.toFixed(1);
  return `${formatted} ${value === 1 ? "day" : "days"}`;
}

function getIssueStatusClass(issueKey: string, issuesByKey: Record<string, Issue>) {
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

function renderRiskAgingCard(
  title: string,
  group: SignalRiskAgingGroup,
  emptyMessage: string,
  issuesByKey: Record<string, Issue>
) {
  const tickets = group.tickets ?? [];

  return (
    <article className="signal-aging-card">
      <strong>{title}</strong>
      {tickets.length > 0 ? (
        <>
          <ul className="metric-ticket-list">
            {tickets.map((ticket) => (
              <li key={ticket.key}>
                <span className={`link-button status-badge ${getIssueStatusClass(ticket.key, issuesByKey)}`}>
                  {ticket.key} ({formatAgeDays(ticket.age_days)})
                </span>
              </li>
            ))}
          </ul>
          <p className="signal-aging-summary">
            Oldest: {formatAgeDays(group.oldest_age_days)}, Average: {formatAgeDays(group.average_age_days)}
            {group.unknown_count > 0 ? ` · ${group.unknown_count} age${group.unknown_count === 1 ? "" : "s"} unavailable` : ""}
          </p>
        </>
      ) : (
        <p className="muted">{emptyMessage}</p>
      )}
    </article>
  );
}

function formatDeltaNumber(value: number) {
  const formatted = Number.isInteger(value) ? value.toFixed(0) : value.toFixed(1);
  return value > 0 ? `+${formatted}` : formatted;
}

function formatLast24HoursItem(item: SignalLast24HoursItem) {
  if (item.delta === null) {
    return `${item.label} N/A`;
  }
  if (item.value_type === "percentage") {
    return `${item.label} ${formatDeltaNumber(item.delta)}%`;
  }

  const absoluteDelta = Math.abs(item.delta);
  const label = absoluteDelta === 1 ? item.label : `${item.label}s`;
  return `${formatDeltaNumber(item.delta)} ${label}`;
}

function renderLast24HoursItem(item: SignalLast24HoursItem) {
  return (
    <li className={`signal-delta-item ${item.impact}`} key={item.metric_name}>
      <span>{formatLast24HoursItem(item)}</span>
    </li>
  );
}

function signalHealthScore(signalValue: string): number | null {
  if (signalValue === "GREEN") {
    return 3;
  }
  if (signalValue === "YELLOW") {
    return 2;
  }
  if (signalValue === "RED") {
    return 1;
  }
  return null;
}

function getSignalTrend(rows: ReleaseSignalTrendRow[]): SignalTrend | null {
  const scores = rows
    .map((row) => signalHealthScore(row.signal))
    .filter((score): score is number => score !== null);
  if (scores.length < 2) {
    return null;
  }

  const difference = scores[scores.length - 1] - scores[0];
  if (difference > 0) {
    return "increasing";
  }
  if (difference < 0) {
    return "decreasing";
  }
  return "similar";
}

function getSignalTrendTooltip(trend: SignalTrend) {
  if (trend === "increasing") {
    return "Based on the last 3 releases, release signal health is improving.";
  }
  if (trend === "decreasing") {
    return "Based on the last 3 releases, release signal health is decreasing.";
  }
  return "Based on the last 3 releases, release signal health is similar.";
}

function renderLast24HoursSection(signal: ReleaseSignalResponse) {
  return (
    <div className="signal-readiness-section signal-column-section">
      <h3>Last 24 Hours</h3>
      {signal.last_24_hours.has_baseline && signal.last_24_hours.items.length > 0 ? (
        <ul className="signal-delta-list">{signal.last_24_hours.items.map(renderLast24HoursItem)}</ul>
      ) : (
        <p className="muted">No 24-hour baseline snapshot available.</p>
      )}
    </div>
  );
}

function renderReleaseGatesSection(signal: ReleaseSignalResponse) {
  return (
    <div className="signal-readiness-section signal-column-section">
      <h3>Release Gates</h3>
      {signal.release_gates.length > 0 ? (
        <ul className="signal-gate-list">{signal.release_gates.map(renderReleaseGate)}</ul>
      ) : (
        <p className="muted">No release gates available.</p>
      )}
    </div>
  );
}

function renderCriticalRisksSection(signal: ReleaseSignalResponse) {
  return (
    <div className="signal-readiness-section">
      <h3>Critical Risks</h3>
      {signal.critical_risks.length > 0 ? (
        <ul className="signal-risk-list">{signal.critical_risks.map(renderRiskItem)}</ul>
      ) : (
        <p className="muted">No critical risks.</p>
      )}
    </div>
  );
}

function renderPrimaryRiskSection(signal: ReleaseSignalResponse) {
  if (!signal.primary_risk) {
    return null;
  }

  return (
    <div className="signal-readiness-section">
      <h3>Primary Risk</h3>
      <p>{signal.primary_risk.message}</p>
    </div>
  );
}

function renderRiskAgingSection(signal: ReleaseSignalResponse, issuesByKey: Record<string, Issue>) {
  return (
    <div className="signal-readiness-section">
      <h3>Risk Aging</h3>
      <div className="signal-aging-grid">
        {renderRiskAgingCard("Blockers", signal.risk_aging.blockers, "No blockers.", issuesByKey)}
        {renderRiskAgingCard(
          "High-severity bugs",
          signal.risk_aging.high_severity_bugs,
          "No high-severity bugs.",
          issuesByKey
        )}
      </div>
    </div>
  );
}

function renderWarningsSection(signal: ReleaseSignalResponse) {
  return (
    <div className="signal-readiness-section">
      <h3>Warnings</h3>
      {signal.warnings.length > 0 ? (
        <ul className="signal-risk-list">{signal.warnings.map(renderRiskItem)}</ul>
      ) : (
        <p className="muted">No warnings.</p>
      )}
    </div>
  );
}

export function SignalSummaryPanel({ signal, isLoading, releases, selectedProjectKey, refreshNonce }: SignalSummaryPanelProps) {
  const recentReleases = useMemo(
    () => getRecentProjectReleases(releases, selectedProjectKey, 3),
    [releases, selectedProjectKey]
  );
  const riskAgingIssueKeys = useMemo(() => {
    if (!signal) {
      return [];
    }

    return Array.from(
      new Set([
        ...(signal.risk_aging.blockers.tickets ?? []).map((ticket) => ticket.key),
        ...(signal.risk_aging.high_severity_bugs.tickets ?? []).map((ticket) => ticket.key),
      ])
    );
  }, [signal]);
  const [signalTrendRows, setSignalTrendRows] = useState<ReleaseSignalTrendRow[]>([]);
  const [riskAgingIssuesByKey, setRiskAgingIssuesByKey] = useState<Record<string, Issue>>({});
  const [isSignalExpanded, setIsSignalExpanded] = useState(true);
  const signalTrend = useMemo(() => getSignalTrend(signalTrendRows), [signalTrendRows]);
  const signalTrendTooltip = signalTrend ? getSignalTrendTooltip(signalTrend) : null;
  const statusLabel = signalStatusLabel(signal);
  const confidenceLabel = signal?.confidence_score !== null && signal?.confidence_score !== undefined
    ? `${signal.confidence_score.toFixed(0)}%`
    : "N/A";
  const summary = signal?.summary ?? signalDescription(signal?.signal ?? null);

  useEffect(() => {
    if (recentReleases.length === 0) {
      setSignalTrendRows([]);
      return;
    }

    let isActive = true;

    async function loadRecentSignals() {
      try {
        const results = await Promise.all(
          recentReleases.map(async (release) => {
            const response = await apiClient.getSignal(release.release_id);
            if (!response.signal) {
              return null;
            }
            return {
              release_id: release.release_id,
              signal: response.signal,
            };
          })
        );

        if (isActive) {
          const validRows = results.filter((row): row is ReleaseSignalTrendRow => row !== null);
          setSignalTrendRows(validRows);
        }
      } catch {
        if (isActive) {
          setSignalTrendRows([]);
        }
      }
    }

    void loadRecentSignals();

    return () => {
      isActive = false;
    };
  }, [recentReleases, refreshNonce]);

  useEffect(() => {
    if (riskAgingIssueKeys.length === 0) {
      setRiskAgingIssuesByKey({});
      return;
    }

    let isActive = true;

    async function loadRiskAgingIssues() {
      const issueResults = await Promise.allSettled(riskAgingIssueKeys.map((issueKey) => apiClient.getIssue(issueKey)));
      const issuesByKey: Record<string, Issue> = {};
      for (const result of issueResults) {
        if (result.status === "fulfilled") {
          issuesByKey[result.value.issue_key] = result.value;
        }
      }

      if (isActive) {
        setRiskAgingIssuesByKey(issuesByKey);
      }
    }

    void loadRiskAgingIssues();

    return () => {
      isActive = false;
    };
  }, [riskAgingIssueKeys]);

  return (
    <section className="panel signal-panel">
      <div className="panel-heading">
        <h2>Release Confidence Signal</h2>
        <div className="panel-heading-actions">
          <div className="signal-value-group">
            <span className={signalClassName(signal?.signal ?? null)}>{statusLabel}</span>
            <span className="signal-confidence-badge">Confidence {confidenceLabel}</span>
            {signalTrend && signalTrendTooltip ? (
              <span
                className={`confidence-trend-icon signal-trend-icon ${signalTrend}`}
                title={signalTrendTooltip}
                aria-label={signalTrendTooltip}
                role="img"
                tabIndex={0}
              />
            ) : null}
          </div>
          <button
            type="button"
            className="secondary-button compact-button"
            aria-expanded={isSignalExpanded}
            onClick={() => setIsSignalExpanded((current) => !current)}
          >
            {isSignalExpanded ? "Minimize" : "Expand"}
          </button>
        </div>
      </div>
      {!isLoading && signal?.confidence_breakdown ? (
        <ConfidenceBreakdownCard breakdown={signal.confidence_breakdown} />
      ) : null}
      {!isLoading && signal?.biggest_driver ? (
        <BiggestDriverCard driver={signal.biggest_driver} heading="Biggest Confidence Drag" />
      ) : null}
      {isSignalExpanded ? (
        <>
          <p className="signal-description">{summary}</p>
          {isLoading ? <p className="muted">Loading signal...</p> : null}
          {!isLoading && signal ? (
            <div className="signal-two-column-section">
              {renderLast24HoursSection(signal)}
              {renderReleaseGatesSection(signal)}
            </div>
          ) : null}
          {!isLoading && signal ? renderCriticalRisksSection(signal) : null}
          {!isLoading && signal ? renderPrimaryRiskSection(signal) : null}
          {!isLoading && signal ? renderRiskAgingSection(signal, riskAgingIssuesByKey) : null}
          {!isLoading && signal ? renderWarningsSection(signal) : null}
          {!isLoading && signal && signal.reasons.length === 0 ? (
            <p className="muted">Signal has not been computed yet.</p>
          ) : null}
          {!isLoading && signal?.updated_at ? (
            <p className="timestamp">Updated {new Date(signal.updated_at).toLocaleString()}</p>
          ) : null}
        </>
      ) : null}

    </section>
  );
}
