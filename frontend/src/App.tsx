import { useEffect, useState } from "react";

import { apiClient } from "./api/client";
import type {
  Release,
  ReleaseChartsResponse,
  ReleaseMetricsResponse,
  ReleaseSignalResponse,
} from "./api/types";
import { AdminPanel } from "./components/AdminPanel";
import { ChartsPanel } from "./components/ChartsPanel";
import { Header } from "./components/Header";
import { IssueDetailModal } from "./components/IssueDetailModal";
import { IssuesPanel } from "./components/IssuesPanel";
import { MetricsPanel } from "./components/MetricsPanel";
import { ReleaseSelector } from "./components/ReleaseSelector";
import { SignalSummaryPanel } from "./components/SignalSummaryPanel";
import { SprintsPanel } from "./components/SprintsPanel";
import { getCurrentReleaseId } from "./releaseSelection";

type AppTab = "dashboard" | "sprints" | "admin";

export default function App() {
  const [releases, setReleases] = useState<Release[]>([]);
  const [selectedReleaseId, setSelectedReleaseId] = useState<string | null>(null);
  const [selectedRelease, setSelectedRelease] = useState<Release | null>(null);
  const [metrics, setMetrics] = useState<ReleaseMetricsResponse | null>(null);
  const [charts, setCharts] = useState<ReleaseChartsResponse | null>(null);
  const [signal, setSignal] = useState<ReleaseSignalResponse | null>(null);
  const [isLoadingReleases, setIsLoadingReleases] = useState(true);
  const [isLoadingDetails, setIsLoadingDetails] = useState(false);
  const [isRecomputingRelease, setIsRecomputingRelease] = useState(false);
  const [isRecomputingAll, setIsRecomputingAll] = useState(false);
  const [recomputeMessage, setRecomputeMessage] = useState<string | null>(null);
  const [dashboardRefreshNonce, setDashboardRefreshNonce] = useState(0);
  const [selectedTab, setSelectedTab] = useState<AppTab>("dashboard");
  const [selectedIssueKey, setSelectedIssueKey] = useState<string | null>(null);
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
        setSelectedReleaseId((current) => current ?? getCurrentReleaseId(response.items));
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

  async function handleRecomputeAll() {
    if (releases.length === 0 || isRecomputingAll) {
      return;
    }

    setIsRecomputingAll(true);
    setErrorMessage(null);
    setRecomputeMessage("Recomputing snapshots for all releases...");

    try {
      const result = await apiClient.recomputeAllSnapshots();
      if (result.releases_failed > 0) {
        const failedReleaseIds = result.errors.map((error) => error.release_id).join(", ");
        setRecomputeMessage(
          `Recompute finished: ${result.releases_recomputed}/${result.releases_total} releases succeeded, ${result.releases_failed} failed (${failedReleaseIds}).`
        );
      } else {
        setRecomputeMessage(`Recompute complete for ${result.releases_recomputed}/${result.releases_total} releases.`);
      }
      setDashboardRefreshNonce((current) => current + 1);
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : "Failed to recompute snapshots.");
    } finally {
      setIsRecomputingAll(false);
    }
  }

  async function handleRecomputeRelease() {
    if (!selectedReleaseId || isRecomputingRelease) {
      return;
    }

    setIsRecomputingRelease(true);
    setErrorMessage(null);
    try {
      await apiClient.recomputeRelease(selectedReleaseId);
      setDashboardRefreshNonce((current) => current + 1);
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : "Failed to recompute release metrics.");
    } finally {
      setIsRecomputingRelease(false);
    }
  }

  function handleOperationalDataChanged() {
    setDashboardRefreshNonce((current) => current + 1);
  }

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
  }, [selectedReleaseId, dashboardRefreshNonce]);

  return (
    <div className="app-shell">
      <Header
        title="LighthousePM"
        subtitle={
          ""
        }
      />

      <nav className="tab-row" aria-label="Dashboard sections">
        <button
          type="button"
          className={`tab-button ${selectedTab === "dashboard" ? "active" : ""}`}
          onClick={() => setSelectedTab("dashboard")}
        >
          Releases
        </button>
        <button
          type="button"
          className={`tab-button ${selectedTab === "sprints" ? "active" : ""}`}
          onClick={() => setSelectedTab("sprints")}
        >
          Sprints
        </button>
        <button
          type="button"
          className={`tab-button ${selectedTab === "admin" ? "active" : ""}`}
          onClick={() => setSelectedTab("admin")}
        >
          Admin
        </button>
      </nav>

      <main className="dashboard-grid">
        {selectedTab === "dashboard" ? (
          <ReleaseSelector
            releases={releases}
            selectedReleaseId={selectedReleaseId}
            selectedRelease={selectedRelease}
            isLoading={isLoadingReleases}
            isRecomputing={isRecomputingRelease}
            onChange={setSelectedReleaseId}
            onRecompute={handleRecomputeRelease}
          />
        ) : null}

        {errorMessage && selectedTab === "dashboard" ? <div className="panel error-panel">{errorMessage}</div> : null}

        {!isLoadingReleases && releases.length === 0 && selectedTab !== "admin" && selectedTab !== "sprints" ? (
          <section className="panel empty-panel">
            <h2>No releases</h2>
            <p className="muted">Seed data or sync Jira to populate the dashboard.</p>
          </section>
        ) : null}

        {selectedReleaseId && selectedTab === "dashboard" ? (
          <>
            <SignalSummaryPanel
              signal={signal}
              isLoading={isLoadingDetails}
              releases={releases}
              refreshNonce={dashboardRefreshNonce}
            />
            <MetricsPanel
              metrics={metrics}
              charts={charts}
              isLoading={isLoadingDetails}
              onSelectIssue={setSelectedIssueKey}
            />
            <IssuesPanel
              releaseId={selectedReleaseId}
              refreshNonce={dashboardRefreshNonce}
              onSelectIssue={setSelectedIssueKey}
            />
            <ChartsPanel
              charts={charts}
              releases={releases}
              selectedReleaseName={selectedRelease?.name ?? null}
              refreshNonce={dashboardRefreshNonce}
              isLoading={isLoadingDetails}
            />
          </>
        ) : null}

        {selectedTab === "sprints" ? (
          <SprintsPanel refreshNonce={dashboardRefreshNonce} onSelectIssue={setSelectedIssueKey} />
        ) : null}

        {selectedTab === "admin" ? (
          <AdminPanel
            onRecomputeAll={handleRecomputeAll}
            isRecomputingAll={isRecomputingAll}
            recomputeMessage={recomputeMessage}
            onOperationalDataChanged={handleOperationalDataChanged}
          />
        ) : null}
      </main>

      <IssueDetailModal issueKey={selectedIssueKey} onClose={() => setSelectedIssueKey(null)} />
    </div>
  );
}
