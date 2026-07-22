import { useEffect, useMemo, useState } from "react";

import { apiClient } from "../api/client";
import type {
  JiraConfigurationResponse,
  Release,
  ReleaseChartsResponse,
  ReleaseMetricsResponse,
  ReleaseSignalResponse,
} from "../api/types";
import { formatRecomputeAllMessage } from "./releaseWorkspaceMessages";
import {
  getSelectedWorkspaceReleaseId,
  getWorkspaceReleases,
  normalizeProjectKey,
  releaseBelongsToProject,
  resolveWorkspaceReleaseId,
} from "../workspaceContext";

export type ReleaseWorkspace = {
  activeProjectKey: string | null;
  workspaceReleases: Release[];
  selectedReleaseId: string | null;
  selectedRelease: Release | null;
  metrics: ReleaseMetricsResponse | null;
  charts: ReleaseChartsResponse | null;
  signal: ReleaseSignalResponse | null;
  isLoadingReleases: boolean;
  isLoadingDetails: boolean;
  isRecomputingRelease: boolean;
  isRecomputingAll: boolean;
  recomputeMessage: string | null;
  refreshNonce: number;
  errorMessage: string | null;
  configurationRequired: boolean;
  setSelectedReleaseId: (releaseId: string | null) => void;
  handleRecomputeAll: () => Promise<void>;
  handleRecomputeRelease: () => Promise<void>;
  handleOperationalDataChanged: () => void;
  handleConfigurationSaved: (config: JiraConfigurationResponse) => void;
};

function errorMessage(error: unknown, fallback: string) {
  return error instanceof Error ? error.message : fallback;
}

export function useReleaseWorkspace(): ReleaseWorkspace {
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
  const [refreshNonce, setRefreshNonce] = useState(0);
  const [workspaceErrorMessage, setWorkspaceErrorMessage] = useState<string | null>(null);
  const [configurationRequired, setConfigurationRequired] = useState(false);

  function applyActiveProjectKey(projectKey: string | null | undefined) {
    const normalizedProjectKey = normalizeProjectKey(projectKey);
    setActiveProjectKey(normalizedProjectKey);
    setReleases([]);
    setSelectedReleaseId(null);
    setSelectedRelease(null);
    setMetrics(null);
    setCharts(null);
    setSignal(null);
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
        setConfigurationRequired(!config.is_complete);
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

  const workspaceReleases = useMemo(
    () => getWorkspaceReleases(releases, activeProjectKey),
    [activeProjectKey, releases]
  );

  const selectedWorkspaceReleaseId = useMemo(() => {
    return getSelectedWorkspaceReleaseId(workspaceReleases, selectedReleaseId);
  }, [selectedReleaseId, workspaceReleases]);

  useEffect(() => {
    setSelectedReleaseId((current) => resolveWorkspaceReleaseId(workspaceReleases, current));
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
      setWorkspaceErrorMessage(null);
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
        setWorkspaceErrorMessage(errorMessage(error, "Failed to load releases."));
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
  }, [activeProjectKey, refreshNonce, isProjectContextLoaded]);

  async function handleRecomputeAll() {
    if (releases.length === 0 || isRecomputingAll) {
      return;
    }

    setIsRecomputingAll(true);
    setWorkspaceErrorMessage(null);
    setRecomputeMessage("Recomputing snapshots for all releases...");

    try {
      const result = await apiClient.recomputeAllSnapshots();
      setRecomputeMessage(formatRecomputeAllMessage(result));
      setRefreshNonce((current) => current + 1);
    } catch (error) {
      setWorkspaceErrorMessage(errorMessage(error, "Failed to recompute snapshots."));
    } finally {
      setIsRecomputingAll(false);
    }
  }

  async function handleRecomputeRelease() {
    if (!selectedReleaseId || isRecomputingRelease) {
      return;
    }

    setIsRecomputingRelease(true);
    setWorkspaceErrorMessage(null);
    try {
      await apiClient.recomputeRelease(selectedReleaseId);
      setRefreshNonce((current) => current + 1);
    } catch (error) {
      setWorkspaceErrorMessage(errorMessage(error, "Failed to recompute release metrics."));
    } finally {
      setIsRecomputingRelease(false);
    }
  }

  function handleOperationalDataChanged() {
    setRefreshNonce((current) => current + 1);
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
      setWorkspaceErrorMessage(null);
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
        if (!releaseBelongsToProject(release, activeProjectKey)) {
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
        setWorkspaceErrorMessage(errorMessage(error, "Failed to load dashboard data."));
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
  }, [activeProjectKey, selectedWorkspaceReleaseId, refreshNonce]);

  function handleConfigurationSaved(config: JiraConfigurationResponse) {
    applyActiveProjectKey(config.jira_project_key);
    setRefreshNonce((current) => current + 1);
    setConfigurationRequired(!config.is_complete);
    if (config.is_complete) {
      setWorkspaceErrorMessage(null);
    }
  }

  return {
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
    refreshNonce,
    errorMessage: workspaceErrorMessage,
    configurationRequired,
    setSelectedReleaseId,
    handleRecomputeAll,
    handleRecomputeRelease,
    handleOperationalDataChanged,
    handleConfigurationSaved,
  };
}
