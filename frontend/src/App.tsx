import { Component, lazy, Suspense, useEffect, useState, type ReactNode } from "react";

import type { MetricValues, JiraConfigurationResponse } from "./api/types";
import {
  getSprintWorkspaceMode,
  isReleaseWorkspaceTab,
  shouldShowDetailHeader,
  type AppTab,
} from "./appNavigation";
import { AppSidebar } from "./components/AppSidebar";
import { DetailHeader } from "./components/DetailHeader";
import { IssueDetailModal } from "./components/IssueDetailModal";
import { ReleaseWorkspaceControls } from "./components/ReleaseWorkspaceControls";
import { WorkspaceHeader } from "./components/WorkspaceHeader";
import { useReleaseWorkspace } from "./hooks/useReleaseWorkspace";
import { OverviewPage } from "./pages/OverviewPage";

const AdminPanel = lazy(() =>
  import("./components/AdminPanel").then(({ AdminPanel }) => ({ default: AdminPanel }))
);
const SettingsPanel = lazy(() =>
  import("./components/SettingsPanel").then(({ SettingsPanel }) => ({ default: SettingsPanel }))
);
const SprintsPanel = lazy(() =>
  import("./components/SprintsPanel").then(({ SprintsPanel }) => ({ default: SprintsPanel }))
);
const AboutKnowledgePanel = lazy(() =>
  import("./pages/AboutKnowledgePanel").then(({ AboutKnowledgePanel }) => ({ default: AboutKnowledgePanel }))
);
const ReleaseCommandPage = lazy(() =>
  import("./pages/ReleaseCommandPage").then(({ ReleaseCommandPage }) => ({ default: ReleaseCommandPage }))
);
const ReleaseReportsPage = lazy(() =>
  import("./pages/ReleaseReportsPage").then(({ ReleaseReportsPage }) => ({ default: ReleaseReportsPage }))
);

type LazyScreenErrorBoundaryProps = {
  children: ReactNode;
  screenKey: AppTab;
};

type LazyScreenErrorBoundaryState = {
  hasError: boolean;
};

class LazyScreenErrorBoundary extends Component<
  LazyScreenErrorBoundaryProps,
  LazyScreenErrorBoundaryState
> {
  state: LazyScreenErrorBoundaryState = { hasError: false };

  static getDerivedStateFromError(): LazyScreenErrorBoundaryState {
    return { hasError: true };
  }

  componentDidUpdate(previousProps: LazyScreenErrorBoundaryProps) {
    if (previousProps.screenKey !== this.props.screenKey && this.state.hasError) {
      this.setState({ hasError: false });
    }
  }

  render() {
    if (this.state.hasError) {
      return (
        <section className="panel error-panel" role="alert">
          This screen could not be loaded. Try another section, then return here.
        </section>
      );
    }

    return this.props.children;
  }
}

function LazyScreenFallback() {
  return (
    <section className="panel" role="status" aria-live="polite">
      Loading workspace screen...
    </section>
  );
}

export default function App() {
  const {
    activeProjectKey,
    workspaceReleases,
    selectedReleaseId: selectedWorkspaceReleaseId,
    selectedRelease,
    metrics,
    charts,
    signal,
    isLoadingReleases,
    isLoadingDetails,
    isRecomputingRelease,
    isRecomputingAll,
    recomputeMessage,
    refreshNonce: dashboardRefreshNonce,
    errorMessage,
    configurationRequired,
    setSelectedReleaseId,
    handleRecomputeAll,
    handleRecomputeRelease,
    handleOperationalDataChanged,
    handleConfigurationSaved: saveWorkspaceConfiguration,
  } = useReleaseWorkspace();
  const [selectedTab, setSelectedTab] = useState<AppTab>("overview");
  const [selectedIssueKey, setSelectedIssueKey] = useState<string | null>(null);
  const [focusedReleaseMetricName, setFocusedReleaseMetricName] = useState<keyof MetricValues | null>(null);
  const [isSyncingJira, setIsSyncingJira] = useState(false);

  useEffect(() => {
    if (configurationRequired) {
      setSelectedTab("settings");
    }
  }, [configurationRequired]);

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
    setFocusedReleaseMetricName(null);
    saveWorkspaceConfiguration(config);
  }

  const isNavigationLocked = isSyncingJira;
  const sprintWorkspaceMode = getSprintWorkspaceMode(selectedTab);
  const releaseTools = (
    <ReleaseWorkspaceControls
      releases={workspaceReleases}
      selectedReleaseId={selectedWorkspaceReleaseId}
      isLoading={isLoadingReleases}
      isNavigationLocked={isNavigationLocked}
      onSelectRelease={setSelectedReleaseId}
      onOpenDetails={handleOpenReleaseDetails}
    />
  );

  return (
    <div className="app-shell intelligence-shell">
      <AppSidebar
        selectedTab={selectedTab}
        isNavigationLocked={isNavigationLocked}
        onSelectTab={requestTabChange}
      />

      <div className="workspace-shell">
        <WorkspaceHeader
          tab={selectedTab}
          isNavigationLocked={isNavigationLocked}
          releaseTools={releaseTools}
        />

        <main className={selectedTab === "overview" ? "overview-grid" : "dashboard-grid detail-dashboard-grid"}>
          {errorMessage && selectedTab !== "admin" ? (
            <div className="panel error-panel" role="alert">
              {errorMessage}
            </div>
          ) : null}

          {shouldShowDetailHeader(selectedTab) ? (
            <DetailHeader
              tab={selectedTab}
              selectedRelease={selectedRelease}
              releaseTools={selectedTab === "release-reports" ? releaseTools : null}
            />
          ) : null}

          {!isLoadingReleases &&
            workspaceReleases.length === 0 &&
            isReleaseWorkspaceTab(selectedTab) ? (
            <section className="panel empty-panel">
              <h2>No releases</h2>
              <p className="muted">Seed data or sync Jira to populate the dashboard.</p>
            </section>
          ) : null}

          {selectedWorkspaceReleaseId && selectedTab === "overview" ? (
            <OverviewPage
              projectKey={activeProjectKey}
              releaseId={selectedWorkspaceReleaseId}
              release={selectedRelease}
              metrics={metrics}
              charts={charts}
              signal={signal}
              refreshNonce={dashboardRefreshNonce}
              isLoading={isLoadingDetails}
              onOpenReports={() => requestTabChange("release-reports")}
              onOpenReleaseMetric={handleOpenReleaseMetric}
            />
          ) : null}

          <LazyScreenErrorBoundary screenKey={selectedTab}>
            <Suspense fallback={<LazyScreenFallback />}>
              {selectedTab === "release-command" ? (
                <ReleaseCommandPage
                  releases={workspaceReleases}
                  selectedProjectKey={activeProjectKey}
                  selectedReleaseId={selectedWorkspaceReleaseId}
                  selectedRelease={selectedRelease}
                  metrics={metrics}
                  charts={charts}
                  signal={signal}
                  refreshNonce={dashboardRefreshNonce}
                  isLoadingReleases={isLoadingReleases}
                  isLoadingDetails={isLoadingDetails}
                  isRecomputingRelease={isRecomputingRelease}
                  focusedMetricName={focusedReleaseMetricName}
                  onSelectRelease={setSelectedReleaseId}
                  onRecomputeRelease={handleRecomputeRelease}
                  onSelectIssue={setSelectedIssueKey}
                />
              ) : null}

              {selectedWorkspaceReleaseId && selectedTab === "release-reports" ? (
                <ReleaseReportsPage
                  releases={workspaceReleases}
                  selectedProjectKey={activeProjectKey}
                  selectedReleaseId={selectedWorkspaceReleaseId}
                  selectedRelease={selectedRelease}
                  metrics={metrics}
                  charts={charts}
                  signal={signal}
                  refreshNonce={dashboardRefreshNonce}
                  isLoading={isLoadingDetails}
                  onSelectIssue={setSelectedIssueKey}
                />
              ) : null}

              {sprintWorkspaceMode ? (
                <SprintsPanel
                  refreshNonce={dashboardRefreshNonce}
                  onSelectIssue={setSelectedIssueKey}
                  mode={sprintWorkspaceMode}
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

              {selectedTab === "about-overview" ? <AboutKnowledgePanel page="overview" /> : null}
              {selectedTab === "about-releases" ? <AboutKnowledgePanel page="releases" /> : null}
              {selectedTab === "about-sprints" ? <AboutKnowledgePanel page="sprints" /> : null}
            </Suspense>
          </LazyScreenErrorBoundary>
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
