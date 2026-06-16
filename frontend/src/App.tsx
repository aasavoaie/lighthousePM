import { useEffect, useMemo, useState } from "react";

import { apiClient } from "./api/client";
import type {
  MetricValues,
  JiraConfigurationResponse,
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
import { ReportExportActions } from "./components/ReportExportActions";
import { ReleaseSelector } from "./components/ReleaseSelector";
import { SettingsPanel } from "./components/SettingsPanel";
import { SignalSummaryPanel } from "./components/SignalSummaryPanel";
import { SprintsPanel } from "./components/SprintsPanel";
import { getCurrentReleaseId, resolveSelectedReleaseId } from "./releaseSelection";

type AppTab =
  | "overview"
  | "release-command"
  | "release-reports"
  | "sprint-intelligence"
  | "sprint-reports"
  | "admin"
  | "settings"
  | "about";

const tabContent: Record<AppTab, { title: string; subtitle: string; kicker: string }> = {
  overview: {
    title: "Risk & Intelligence Platform",
    subtitle: "Intelligent insights to help you ship with confidence.",
    kicker: "Overview",
  },
  "release-command": {
    title: "Release Command Center",
    subtitle: "Review readiness, metrics, and release tickets in one operational view.",
    kicker: "Release Health",
  },
  "release-reports": {
    title: "Reports & Evidence",
    subtitle: "Inspect confidence history, risk contribution, blocker aging, and ticket detail.",
    kicker: "Release Reports",
  },
  "sprint-intelligence": {
    title: "Sprint Intelligence",
    subtitle: "Track delivery confidence, sprint flow, scope movement, and active work.",
    kicker: "Sprint Health",
  },
  "sprint-reports": {
    title: "Reports & Evidence",
    subtitle: "Inspect sprint confidence history, reliability, scope movement, quality, flow, and risk heatmaps.",
    kicker: "Sprint Reports",
  },
  admin: {
    title: "Operations Console",
    subtitle: "Run Jira ingestion and recompute deterministic snapshots for the workspace.",
    kicker: "Admin",
  },
  settings: {
    title: "Settings",
    subtitle: "Configure Jira sync for the local workspace.",
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
  const isReleaseTab = tab === "release-reports";
  return (
    <section className="detail-hero">
      <div>
        <p className="detail-hero-kicker">{content.kicker}</p>
        <h2>{content.title}</h2>
        <p>{content.subtitle}</p>
      </div>
      {selectedRelease && isReleaseTab ? (
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

function isJiraConfigurationComplete(config: JiraConfigurationResponse) {
  return config.is_complete;
}

function normalizeProjectKey(projectKey: string | null | undefined) {
  const normalized = projectKey?.trim().toUpperCase();
  return normalized ? normalized : null;
}

export default function App() {
  const [releases, setReleases] = useState<Release[]>([]);
  const [activeProjectKey, setActiveProjectKey] = useState<string | null>(null);
  const [isProjectContextLoaded, setIsProjectContextLoaded] = useState(false);
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
  const [focusedReleaseMetricName, setFocusedReleaseMetricName] = useState<keyof MetricValues | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [isSyncingJira, setIsSyncingJira] = useState(false);

  function applyActiveProjectKey(projectKey: string | null | undefined) {
    const normalizedProjectKey = normalizeProjectKey(projectKey);
    setActiveProjectKey(normalizedProjectKey);
    setReleases([]);
    setSelectedReleaseId(null);
    setSelectedRelease(null);
    setMetrics(null);
    setCharts(null);
    setSignal(null);
    setFocusedReleaseMetricName(null);
    setIsLoadingDetails(false);
    setIsLoadingReleases(Boolean(normalizedProjectKey));
  }

  useEffect(() => {
    let isActive = true;

    async function loadProjectContext() {
      try {
        const config = await apiClient.getJiraConfiguration();
        if (!isActive) {
          return;
        }
        applyActiveProjectKey(config.jira_project_key);
        if (!isJiraConfigurationComplete(config)) {
          setSelectedTab("settings");
        }
      } catch {
        // Keep the dashboard usable if setup state cannot be loaded.
      } finally {
        if (isActive) {
          setIsProjectContextLoaded(true);
        }
      }
    }

    void loadProjectContext();

    return () => {
      isActive = false;
    };
  }, []);

  const workspaceReleases = useMemo(() => {
    if (!activeProjectKey) {
      return releases;
    }
    return releases.filter((release) => normalizeProjectKey(release.project_key) === activeProjectKey);
  }, [activeProjectKey, releases]);

  const selectedWorkspaceReleaseId = useMemo(() => {
    if (!selectedReleaseId) {
      return null;
    }
    return workspaceReleases.some((release) => release.release_id === selectedReleaseId) ? selectedReleaseId : null;
  }, [selectedReleaseId, workspaceReleases]);

  useEffect(() => {
    setSelectedReleaseId((current) => resolveSelectedReleaseId(workspaceReleases, current));
  }, [workspaceReleases]);

  useEffect(() => {
    let isActive = true;

    async function loadReleases() {
      if (!isProjectContextLoaded) {
        return;
      }
      if (!activeProjectKey) {
        setReleases([]);
        setIsLoadingReleases(false);
        return;
      }

      setIsLoadingReleases(true);
      setErrorMessage(null);
      try {
        const response = await apiClient.getReleases(activeProjectKey);
        if (!isActive) {
          return;
        }
        setReleases(response.items);
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
  }, [activeProjectKey, dashboardRefreshNonce, isProjectContextLoaded]);

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

  function requestTabChange(tab: AppTab) {
    if (isSyncingJira) {
      return;
    }
    setSelectedTab(tab);
  }

  function handleOpenReleaseDetails() {
    if (isSyncingJira) {
      return;
    }
    setFocusedReleaseMetricName(null);
    setSelectedTab("release-command");
  }

  function handleOpenReleaseMetric(metricName: keyof MetricValues) {
    if (isSyncingJira) {
      return;
    }
    setFocusedReleaseMetricName(metricName);
    setSelectedTab("release-command");
  }

  useEffect(() => {
    if (!selectedWorkspaceReleaseId) {
      setSelectedRelease(null);
      setMetrics(null);
      setCharts(null);
      setSignal(null);
      return;
    }

    const currentReleaseId = selectedWorkspaceReleaseId;
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
        if (activeProjectKey && normalizeProjectKey(release.project_key) !== activeProjectKey) {
          setSelectedRelease(null);
          setMetrics(null);
          setCharts(null);
          setSignal(null);
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
  }, [activeProjectKey, selectedWorkspaceReleaseId, dashboardRefreshNonce]);

  useEffect(() => {
    if (selectedTab !== "release-command" || !focusedReleaseMetricName) {
      return;
    }

    const timeoutId = window.setTimeout(() => {
      document.getElementById(`release-metric-${focusedReleaseMetricName}`)?.scrollIntoView({
        behavior: "smooth",
        block: "center",
      });
    }, 100);

    return () => window.clearTimeout(timeoutId);
  }, [focusedReleaseMetricName, selectedTab]);

  function handleConfigurationSaved(config: JiraConfigurationResponse) {
    applyActiveProjectKey(config.jira_project_key);
    setDashboardRefreshNonce((current) => current + 1);
    if (isJiraConfigurationComplete(config)) {
      setErrorMessage(null);
    }
  }

  const currentReleaseId = getCurrentReleaseId(workspaceReleases);
  const showReleaseControls =
    selectedTab === "overview" || selectedTab === "release-command" || selectedTab === "release-reports";
  const workspaceContent = tabContent[selectedTab];
  const isNavigationLocked = isSyncingJira;

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
            disabled={isNavigationLocked}
            onClick={() => requestTabChange("overview")}
          >
            <span className="nav-icon nav-overview" aria-hidden="true" />
            Overview
          </button>
          <div className="sidebar-menu-group">
            <div className="sidebar-group-label">
              <span className="nav-icon nav-releases" aria-hidden="true" />
              Releases
            </div>
            <div className="sidebar-submenu">
              <button
                type="button"
                className={`sidebar-sublink ${selectedTab === "release-command" ? "active" : ""}`}
                disabled={isNavigationLocked}
                onClick={() => requestTabChange("release-command")}
              >
                Command Center
              </button>
              <button
                type="button"
                className={`sidebar-sublink ${selectedTab === "release-reports" ? "active" : ""}`}
                disabled={isNavigationLocked}
                onClick={() => requestTabChange("release-reports")}
              >
                Reports &amp; Evidence
              </button>
            </div>
          </div>
          <div className="sidebar-menu-group">
            <div className="sidebar-group-label">
              <span className="nav-icon nav-sprints" aria-hidden="true" />
              Sprints
            </div>
            <div className="sidebar-submenu">
              <button
                type="button"
                className={`sidebar-sublink ${selectedTab === "sprint-intelligence" ? "active" : ""}`}
                disabled={isNavigationLocked}
                onClick={() => requestTabChange("sprint-intelligence")}
              >
                Sprint Intelligence
              </button>
              <button
                type="button"
                className={`sidebar-sublink ${selectedTab === "sprint-reports" ? "active" : ""}`}
                disabled={isNavigationLocked}
                onClick={() => requestTabChange("sprint-reports")}
              >
                Reports &amp; Evidence
              </button>
            </div>
          </div>
          <button
            type="button"
            className={`sidebar-link ${selectedTab === "admin" ? "active" : ""}`}
            disabled={isNavigationLocked}
            onClick={() => requestTabChange("admin")}
          >
            <span className="nav-icon nav-admin" aria-hidden="true" />
            Admin
          </button>
        </nav>
        <div className="sidebar-footer">
          <button
            type="button"
            className={`sidebar-link subtle ${selectedTab === "settings" ? "active" : ""}`}
            disabled={isNavigationLocked}
            onClick={() => requestTabChange("settings")}
          >
            <span className="nav-icon nav-settings" aria-hidden="true" />
            Settings
          </button>
          <button
            type="button"
            className={`sidebar-link subtle ${selectedTab === "about" ? "active" : ""}`}
            disabled={isNavigationLocked}
            onClick={() => requestTabChange("about")}
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
            {isNavigationLocked ? <p className="workspace-lock-message">Jira sync is running. Navigation is locked until it finishes.</p> : null}
          </div>
          {showReleaseControls ? (
            <div className="workspace-release-tools">
              <label className="workspace-release-select">
                <span>Release:</span>
                <select
                  disabled={isLoadingReleases || workspaceReleases.length === 0 || isNavigationLocked}
                  value={selectedWorkspaceReleaseId ?? ""}
                  onChange={(event) => setSelectedReleaseId(event.target.value)}
                >
                  {workspaceReleases.length === 0 ? <option value="">No releases</option> : null}
                  {workspaceReleases.map((release) => (
                    <option key={release.release_id} value={release.release_id}>
                      {release.release_id === currentReleaseId ? `${release.name}` : `${release.name}`}
                    </option>
                  ))}
                </select>
              </label>
              <button type="button" className="details-link-button" disabled={isNavigationLocked} onClick={handleOpenReleaseDetails}>
                View details
              </button>
            </div>
          ) : null}
        </header>

        <main className={selectedTab === "overview" ? "overview-grid" : "dashboard-grid detail-dashboard-grid"}>
          {errorMessage && selectedTab !== "admin" ? <div className="panel error-panel">{errorMessage}</div> : null}

          {selectedTab !== "overview" &&
          selectedTab !== "admin" &&
          selectedTab !== "release-command" &&
          selectedTab !== "sprint-intelligence"
            ? renderDetailHeader(selectedTab, selectedRelease)
            : null}

          {!isLoadingReleases &&
          workspaceReleases.length === 0 &&
          (selectedTab === "overview" || selectedTab === "release-command" || selectedTab === "release-reports") ? (
            <section className="panel empty-panel">
              <h2>No releases</h2>
              <p className="muted">Seed data or sync Jira to populate the dashboard.</p>
            </section>
          ) : null}

          {selectedWorkspaceReleaseId && selectedTab === "overview" ? (
            <>
              <section className="panel report-export-panel overview-export-panel">
                <div className="panel-heading">
                  <div>
                    <h2>Executive Reporting</h2>
                  </div>
                  <ReportExportActions
                    entity="overview"
                    entityId={selectedWorkspaceReleaseId}
                    filenameLabel={selectedRelease?.name ?? selectedWorkspaceReleaseId}
                  />
                </div>
              </section>
              <OverviewDashboard
                projectKey={activeProjectKey}
                release={selectedRelease}
                metrics={metrics}
                charts={charts}
                signal={signal}
                refreshNonce={dashboardRefreshNonce}
                isLoading={isLoadingDetails}
                onOpenReports={() => requestTabChange("release-reports")}
                onOpenReleaseMetric={handleOpenReleaseMetric}
              />
            </>
          ) : null}

        {selectedWorkspaceReleaseId && selectedTab === "release-command" ? (
          <>
            <section className="panel report-export-panel">
              <div className="panel-heading">
                <div>
                  <h2>Executive Reporting</h2>
                </div>
                <ReportExportActions
                  entity="release"
                  entityId={selectedWorkspaceReleaseId}
                  filenameLabel={selectedRelease?.name ?? selectedWorkspaceReleaseId}
                />
                <ReportExportActions
                  entity="overview"
                  entityId={selectedWorkspaceReleaseId}
                  filenameLabel={selectedRelease?.name ?? selectedWorkspaceReleaseId}
                />
              </div>
            </section>
            <SignalSummaryPanel
              signal={signal}
              isLoading={isLoadingDetails}
              releases={workspaceReleases}
              selectedProjectKey={activeProjectKey}
              refreshNonce={dashboardRefreshNonce}
            />
            <MetricsPanel
              metrics={metrics}
              charts={charts}
              isLoading={isLoadingDetails}
              onSelectIssue={setSelectedIssueKey}
              focusedMetricName={focusedReleaseMetricName}
            />
          </>
        ) : null}

        {selectedTab === "release-command" ? (
          <>
            <ReleaseSelector
              releases={workspaceReleases}
              selectedReleaseId={selectedWorkspaceReleaseId}
              selectedRelease={selectedRelease}
              isLoading={isLoadingReleases}
              isRecomputing={isRecomputingRelease}
              onChange={setSelectedReleaseId}
              onRecompute={handleRecomputeRelease}
            />
            {selectedWorkspaceReleaseId ? (
              <IssuesPanel
                releaseId={selectedWorkspaceReleaseId}
                refreshNonce={dashboardRefreshNonce}
                onSelectIssue={setSelectedIssueKey}
              />
            ) : null}
          </>
        ) : null}

        {selectedWorkspaceReleaseId && selectedTab === "release-reports" ? (
          <>
            <ChartsPanel
              charts={charts}
              signal={signal}
              metrics={metrics}
              releases={workspaceReleases}
              selectedProjectKey={activeProjectKey}
              selectedReleaseName={selectedRelease?.name ?? null}
              refreshNonce={dashboardRefreshNonce}
              isLoading={isLoadingDetails}
            />
            <IssuesPanel
              releaseId={selectedWorkspaceReleaseId}
              refreshNonce={dashboardRefreshNonce}
              onSelectIssue={setSelectedIssueKey}
            />
          </>
        ) : null}

        {selectedTab === "sprint-intelligence" ? (
          <SprintsPanel
            refreshNonce={dashboardRefreshNonce}
            onSelectIssue={setSelectedIssueKey}
            mode="intelligence"
            projectKey={activeProjectKey}
          />
        ) : null}

        {selectedTab === "sprint-reports" ? (
          <SprintsPanel
            refreshNonce={dashboardRefreshNonce}
            onSelectIssue={setSelectedIssueKey}
            mode="reports"
            projectKey={activeProjectKey}
          />
        ) : null}

        {selectedTab === "admin" ? (
          <AdminPanel
            onRecomputeAll={handleRecomputeAll}
                isRecomputingAll={isRecomputingAll}
                recomputeMessage={recomputeMessage}
                onOperationalDataChanged={handleOperationalDataChanged}
                onSyncStateChange={setIsSyncingJira}
              />
        ) : null}

        {selectedTab === "settings" ? (
          <SettingsPanel onConfigurationSaved={handleConfigurationSaved} />
        ) : null}

        {selectedTab === "about" ? renderAboutPanel() : null}
        </main>

        {selectedTab === "overview" ? (
          <footer className="overview-bottom-bar">
            <span className="bottom-bulb" aria-hidden="true" />
            <p>Focus on the top recommended actions to improve your release confidence.</p>
          </footer>
        ) : null}
      </div>

      <IssueDetailModal issueKey={selectedIssueKey} onClose={() => setSelectedIssueKey(null)} />
    </div>
  );
}
