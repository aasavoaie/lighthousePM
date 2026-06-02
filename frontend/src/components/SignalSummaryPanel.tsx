import { useEffect, useMemo, useState } from "react";

import { apiClient } from "../api/client";
import type { Release, ReleaseSignalResponse } from "../api/types";
import { MetricColors } from "./ChartComponents";

interface SignalSummaryPanelProps {
  signal: ReleaseSignalResponse | null;
  isLoading: boolean;
  releases: Release[];
  refreshNonce: number;
}

type SignalTrend = "increasing" | "decreasing" | "similar";

type ReleaseSignalTrendRow = {
  release_id: string;
  signal: string;
};

type SignalChartRow = {
  name: string;
  signal_score: number;
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
    return "High release risk: one or more red-threshold conditions are currently triggered.";
  }
  if (signalValue === "YELLOW") {
    return "Moderate release risk: warning conditions are present and should be reviewed.";
  }
  if (signalValue === "GREEN") {
    return "Low release risk: no major threshold violations are currently detected.";
  }
  return "Signal not computed yet for this release snapshot.";
}

function releaseSortTime(release: Release) {
  const primaryDate = release.release_date ?? release.created_at;
  const parsed = Date.parse(primaryDate);
  return Number.isFinite(parsed) ? parsed : 0;
}

function getRecentReleases(releases: Release[]) {
  return [...releases]
    .sort((left, right) => releaseSortTime(right) - releaseSortTime(left))
    .slice(0, 3)
    .reverse();
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

export function SignalSummaryPanel({ signal, isLoading, releases, refreshNonce }: SignalSummaryPanelProps) {
  const recentReleases = useMemo(() => getRecentReleases(releases), [releases]);
  const [signalTrendRows, setSignalTrendRows] = useState<ReleaseSignalTrendRow[]>([]);
  const signalTrend = useMemo(() => getSignalTrend(signalTrendRows), [signalTrendRows]);
  const signalTrendTooltip = signalTrend ? getSignalTrendTooltip(signalTrend) : null;

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

  return (
    <section className="panel signal-panel">
      <div className="panel-heading">
        <h2>Signal</h2>
        <div className="signal-value-group">
          <span className={signalClassName(signal?.signal ?? null)}>{signal?.signal ?? "N/A"}</span>
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
      </div>
      <p className="signal-description">{signalDescription(signal?.signal ?? null)}</p>
      {isLoading ? <p className="muted">Loading signal...</p> : null}
      {!isLoading && signal && signal.reasons.length > 0 ? (
        <ul className="reason-list">
          {signal.reasons.map((reason) => (
            <li key={reason}>{reason}</li>
          ))}
        </ul>
      ) : null}
      {!isLoading && signal && signal.reasons.length === 0 ? (
        <p className="muted">Signal has not been computed yet.</p>
      ) : null}
      {!isLoading && signal?.updated_at ? (
        <p className="timestamp">Updated {new Date(signal.updated_at).toLocaleString()}</p>
      ) : null}

    </section>
  );
}
