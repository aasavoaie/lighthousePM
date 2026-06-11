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
import { IssueDetailModal } from "./components/IssueDetailModal";
import { IssuesPanel } from "./components/IssuesPanel";
import { MetricsPanel } from "./components/MetricsPanel";
import { OverviewDashboard } from "./components/OverviewDashboard";
import { ReleaseSelector } from "./components/ReleaseSelector";
import { SignalSummaryPanel } from "./components/SignalSummaryPanel";
import { SprintsPanel } from "./components/SprintsPanel";
import { getCurrentReleaseId } from "./releaseSelection";

type AppTab = "overview" | "releases" | "sprints" | "reports" | "admin" | "settings" | "about";

const tabContent: Record<AppTab, { title: string; subtitle: string; kicker: string }> = {
  overview: {
    title: "Risk & Intelligence Platform",
    subtitle: "Intelligent insights to help you ship with confidence.",
    kicker: "Overview",
  },
  releases: {
    title: "Release Command Center",
    subtitle: "Review readiness, metrics, and release tickets in one operational view.",
    kicker: "Release Health",
  },
  sprints: {
    title: "Sprint Intelligence",
    subtitle: "Track delivery confidence, sprint flow, scope movement, and active work.",
    kicker: "Sprint Health",
  },
  reports: {
    title: "Reports & Evidence",
    subtitle: "Inspect confidence history, risk contribution, blocker aging, and ticket detail.",
    kicker: "Release Reports",
  },
  admin: {
    title: "Operations Console",
    subtitle: "Run Jira ingestion and recompute deterministic snapshots for the workspace.",
    kicker: "Admin",
  },
  settings: {
    title: "Settings - WIP",
    subtitle: "Workspace preferences and product controls are being prepared.",
    kicker: "Configuration",
  },
  about: {
    title: "About LighthousePM",
    subtitle: "A release intelligence workspace for delivery risk, confidence, and explainable signals.",
    kicker: "Product",
  },
};

function renderDetailHeader(tab: AppTab, selectedRelease: Release | null) {
  const content = tabContent[tab];
  return (
    <section className="detail-hero">
      <div>
        <p className="detail-hero-kicker">{content.kicker}</p>
        <h2>{content.title}</h2>
        <p>{content.subtitle}</p>
      </div>
      {selectedRelease && (tab === "releases" || tab === "reports") ? (
        <dl className="detail-release-meta" aria-label="Selected release summary">
          <div>
            <dt>Project</dt>
            <dd>{selectedRelease.project_key}</dd>
          </div>
          <div>
            <dt>Status</dt>
            <dd>{selectedRelease.status ?? "Unknown"}</dd>
          </div>
          <div>
            <dt>Release</dt>
            <dd>{selectedRelease.release_date ? new Date(selectedRelease.release_date).toLocaleDateString() : "N/A"}</dd>
          </div>
        </dl>
      ) : null}
    </section>
  );
}

function renderSettingsPanel() {
  return (
    <section className="panel product-info-panel">
      <div className="panel-heading">
        <h2>Settings - WIP</h2>
      </div>
      <div className="product-info-grid">
        <article className="product-info-card">
          <span className="product-info-icon nav-settings" aria-hidden="true" />
          <h3>Workspace Preferences</h3>
          <p>Release defaults, team views, and notification preferences will live here.</p>
        </article>
        <article className="product-info-card">
          <span className="product-info-icon nav-admin" aria-hidden="true" />
          <h3>Risk Thresholds</h3>
          <p>Future controls will make signal thresholds visible and adjustable by authorized users.</p>
        </article>
        <article className="product-info-card">
          <span className="product-info-icon nav-reports" aria-hidden="true" />
          <h3>Reporting Views</h3>
          <p>Saved report layouts and preferred operational views are planned for this area.</p>
        </article>
      </div>
    </section>
  );
}

function renderAboutPanel() {
  return (
    <section className="panel product-info-panel">
      <div className="panel-heading">
        <h2>LighthousePM</h2>
      </div>
      <div className="about-product-layout">
        <article className="about-product-summary">
          <h3>What the product does</h3>
          <p>
            LighthousePM turns Jira release and sprint activity into deterministic delivery metrics, release readiness
            signals, and recommended actions. It is built for teams that need a clear view of blockers, quality risk,
            scope movement, flow health, and confidence trends before release decisions are made.
          </p>
        </article>
        <div className="product-info-grid">
          <article className="product-info-card">
            <span className="product-info-icon nav-releases" aria-hidden="true" />
            <h3>Release Intelligence</h3>
            <p>Shows confidence, readiness, critical risks, warnings, tickets, and release-level trend history.</p>
          </article>
          <article className="product-info-card">
            <span className="product-info-icon nav-sprints" aria-hidden="true" />
            <h3>Sprint Intelligence</h3>
            <p>Tracks progress alignment, active work, blockers, sprint-created bugs, rollover, and predictability.</p>
          </article>
          <article className="product-info-card">
            <span className="product-info-icon nav-overview" aria-hidden="true" />
            <h3>Explainable Signals</h3>
            <p>Every confidence signal is tied to explicit metrics, thresholds, reasons, and risk contribution.</p>
          </article>
          <article className="product-info-card">
            <span className="product-info-icon nav-reports" aria-hidden="true" />
            <h3>Operational Evidence</h3>
            <p>Reports preserve the charts, aging detail, comparison data, and ticket context behind each decision.</p>
          </article>
        </div>
      </div>
    </section>
  );
}

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
  const [selectedTab, setSelectedTab] = useState<AppTab>("overview");
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

  const currentReleaseId = getCurrentReleaseId(releases);
  const showReleaseControls = selectedTab === "overview" || selectedTab === "releases" || selectedTab === "reports";
  const workspaceContent = tabContent[selectedTab];

  return (
    <div className="app-shell intelligence-shell">
      <aside className="sidebar-shell" aria-label="Primary">
        <div className="brand-mark">
          <span className="brand-icon" aria-hidden="true" />
          <strong>LighthousePM</strong>
        </div>
        <nav className="sidebar-nav" aria-label="Dashboard sections">
          <button
            type="button"
            className={`sidebar-link ${selectedTab === "overview" ? "active" : ""}`}
            onClick={() => setSelectedTab("overview")}
          >
            <span className="nav-icon nav-overview" aria-hidden="true" />
            Overview
          </button>
          <button
            type="button"
            className={`sidebar-link ${selectedTab === "releases" ? "active" : ""}`}
            onClick={() => setSelectedTab("releases")}
          >
            <span className="nav-icon nav-releases" aria-hidden="true" />
            Releases
          </button>
          <button
            type="button"
            className={`sidebar-link ${selectedTab === "sprints" ? "active" : ""}`}
            onClick={() => setSelectedTab("sprints")}
          >
            <span className="nav-icon nav-sprints" aria-hidden="true" />
            Sprints
          </button>
          <button
            type="button"
            className={`sidebar-link ${selectedTab === "reports" ? "active" : ""}`}
            onClick={() => setSelectedTab("reports")}
          >
            <span className="nav-icon nav-reports" aria-hidden="true" />
            Reports
          </button>
          <button
            type="button"
            className={`sidebar-link ${selectedTab === "admin" ? "active" : ""}`}
            onClick={() => setSelectedTab("admin")}
          >
            <span className="nav-icon nav-admin" aria-hidden="true" />
            Admin
          </button>
        </nav>
        <div className="sidebar-footer">
          <button
            type="button"
            className={`sidebar-link subtle ${selectedTab === "settings" ? "active" : ""}`}
            onClick={() => setSelectedTab("settings")}
          >
            <span className="nav-icon nav-settings" aria-hidden="true" />
            Settings - WIP
          </button>
          <button
            type="button"
            className={`sidebar-link subtle ${selectedTab === "about" ? "active" : ""}`}
            onClick={() => setSelectedTab("about")}
          >
            <span className="nav-icon nav-help" aria-hidden="true" />
            About
          </button>
        </div>
      </aside>

      <div className="workspace-shell">
        <header className="workspace-header">
          <div>
            <h1>{workspaceContent.title}</h1>
            <p>{workspaceContent.subtitle}</p>
          </div>
          {showReleaseControls ? (
            <div className="workspace-release-tools">
              <label className="workspace-release-select">
                <span>Release:</span>
                <select
                  disabled={isLoadingReleases || releases.length === 0}
                  value={selectedReleaseId ?? ""}
                  onChange={(event) => setSelectedReleaseId(event.target.value)}
                >
                  {releases.length === 0 ? <option value="">No releases</option> : null}
                  {releases.map((release) => (
                    <option key={release.release_id} value={release.release_id}>
                      {release.release_id === currentReleaseId ? `${release.name}` : `${release.name}`}
                    </option>
                  ))}
                </select>
              </label>
              <button type="button" className="details-link-button" onClick={() => setSelectedTab("reports")}>
                View details
              </button>
            </div>
          ) : null}
        </header>

        <main className={selectedTab === "overview" ? "overview-grid" : "dashboard-grid detail-dashboard-grid"}>
          {errorMessage && selectedTab !== "admin" ? <div className="panel error-panel">{errorMessage}</div> : null}

          {selectedTab !== "overview" ? renderDetailHeader(selectedTab, selectedRelease) : null}

          {!isLoadingReleases &&
          releases.length === 0 &&
          (selectedTab === "overview" || selectedTab === "releases" || selectedTab === "reports") ? (
            <section className="panel empty-panel">
              <h2>No releases</h2>
              <p className="muted">Seed data or sync Jira to populate the dashboard.</p>
            </section>
          ) : null}

          {selectedReleaseId && selectedTab === "overview" ? (
            <OverviewDashboard
              release={selectedRelease}
              metrics={metrics}
              charts={charts}
              signal={signal}
              isLoading={isLoadingDetails}
              onOpenReports={() => setSelectedTab("reports")}
            />
          ) : null}

        {selectedReleaseId && selectedTab === "releases" ? (
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
          </>
        ) : null}

        {selectedTab === "releases" ? (
          <>
            <ReleaseSelector
              releases={releases}
              selectedReleaseId={selectedReleaseId}
              selectedRelease={selectedRelease}
              isLoading={isLoadingReleases}
              isRecomputing={isRecomputingRelease}
              onChange={setSelectedReleaseId}
              onRecompute={handleRecomputeRelease}
            />
            {selectedReleaseId ? (
              <IssuesPanel
                releaseId={selectedReleaseId}
                refreshNonce={dashboardRefreshNonce}
                onSelectIssue={setSelectedIssueKey}
              />
            ) : null}
          </>
        ) : null}

        {selectedReleaseId && selectedTab === "reports" ? (
          <>
            <ChartsPanel
              charts={charts}
              signal={signal}
              releases={releases}
              selectedReleaseName={selectedRelease?.name ?? null}
              refreshNonce={dashboardRefreshNonce}
              isLoading={isLoadingDetails}
            />
            <IssuesPanel
              releaseId={selectedReleaseId}
              refreshNonce={dashboardRefreshNonce}
              onSelectIssue={setSelectedIssueKey}
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

        {selectedTab === "settings" ? renderSettingsPanel() : null}

        {selectedTab === "about" ? renderAboutPanel() : null}
        </main>

        {selectedTab === "overview" ? (
          <footer className="overview-bottom-bar">
            <span className="bottom-bulb" aria-hidden="true" />
            <p>Focus on the top recommended actions to improve your release confidence.</p>
            <button type="button" className="bottom-minimize-button">
              Minimize
            </button>
          </footer>
        ) : null}
      </div>

      <IssueDetailModal issueKey={selectedIssueKey} onClose={() => setSelectedIssueKey(null)} />
    </div>
  );
}
