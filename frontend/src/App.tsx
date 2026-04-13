import { useEffect, useState } from "react";

import { apiClient } from "./api/client";
import type {
  Release,
  ReleaseChartsResponse,
  ReleaseMetricsResponse,
  ReleaseSignalResponse,
} from "./api/types";
import { ChartsPanel } from "./components/ChartsPanel";
import { Header } from "./components/Header";
import { MetricsPanel } from "./components/MetricsPanel";
import { ReleaseSelector } from "./components/ReleaseSelector";
import { SignalSummaryPanel } from "./components/SignalSummaryPanel";

export default function App() {
  const [releases, setReleases] = useState<Release[]>([]);
  const [selectedReleaseId, setSelectedReleaseId] = useState<string | null>(null);
  const [selectedRelease, setSelectedRelease] = useState<Release | null>(null);
  const [metrics, setMetrics] = useState<ReleaseMetricsResponse | null>(null);
  const [charts, setCharts] = useState<ReleaseChartsResponse | null>(null);
  const [signal, setSignal] = useState<ReleaseSignalResponse | null>(null);
  const [isLoadingReleases, setIsLoadingReleases] = useState(true);
  const [isLoadingDetails, setIsLoadingDetails] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  useEffect(() => {
    let isActive = true;

    async function loadReleases() {
      setIsLoadingReleases(true);
      setErrorMessage(null);
      try {
        const response = await apiClient.getReleases();
        if (!isActive) {
          return;
        }
        setReleases(response.items);
        setSelectedReleaseId((current) => current ?? response.items[0]?.release_id ?? null);
      } catch (error) {
        if (!isActive) {
          return;
        }
        setErrorMessage(error instanceof Error ? error.message : "Failed to load releases.");
      } finally {
        if (isActive) {
          setIsLoadingReleases(false);
        }
      }
    }

    void loadReleases();

    return () => {
      isActive = false;
    };
  }, []);

  useEffect(() => {
    if (!selectedReleaseId) {
      setSelectedRelease(null);
      setMetrics(null);
      setCharts(null);
      setSignal(null);
      return;
    }

    const currentReleaseId = selectedReleaseId;
    let isActive = true;

    async function loadReleaseDashboard() {
      setIsLoadingDetails(true);
      setErrorMessage(null);
      try {
        const [release, metricsResponse, chartsResponse, signalResponse] = await Promise.all([
          apiClient.getRelease(currentReleaseId),
          apiClient.getMetrics(currentReleaseId),
          apiClient.getCharts(currentReleaseId),
          apiClient.getSignal(currentReleaseId),
        ]);
        if (!isActive) {
          return;
        }
        setSelectedRelease(release);
        setMetrics(metricsResponse);
        setCharts(chartsResponse);
        setSignal(signalResponse);
      } catch (error) {
        if (!isActive) {
          return;
        }
        setErrorMessage(error instanceof Error ? error.message : "Failed to load dashboard data.");
      } finally {
        if (isActive) {
          setIsLoadingDetails(false);
        }
      }
    }

    void loadReleaseDashboard();

    return () => {
      isActive = false;
    };
  }, [selectedReleaseId]);

  return (
    <div className="app-shell">
      <Header
        title="LighthousePM"
        subtitle={
          selectedRelease
            ? `${selectedRelease.name} • ${selectedRelease.project_key} • ${selectedRelease.status ?? "Unknown status"}`
            : "Release analytics dashboard"
        }
      />

      <main className="dashboard-grid">
        <ReleaseSelector
          releases={releases}
          selectedReleaseId={selectedReleaseId}
          isLoading={isLoadingReleases}
          onChange={setSelectedReleaseId}
        />

        {errorMessage ? <div className="panel error-panel">{errorMessage}</div> : null}

        {!isLoadingReleases && releases.length === 0 ? (
          <section className="panel empty-panel">
            <h2>No releases</h2>
            <p className="muted">Seed data or sync Jira to populate the dashboard.</p>
          </section>
        ) : null}

        {selectedReleaseId ? (
          <>
            <SignalSummaryPanel signal={signal} isLoading={isLoadingDetails} />
            <MetricsPanel metrics={metrics} isLoading={isLoadingDetails} />
            <ChartsPanel charts={charts} isLoading={isLoadingDetails} />
          </>
        ) : null}
      </main>
    </div>
  );
}