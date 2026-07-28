import type {
  AdminStatusResponse,
  CurrentSprintResponse,
  HealthResponse,
  Issue,
  IssueListResponse,
  JiraConnectionTestResponse,
  JiraConfigurationResponse,
  JiraConfigurationUpdate,
  MetricCatalogResponse,
  RecomputeAllMetricsResponse,
  RecomputeMetricsResponse,
  ReportDepth,
  Release,
  ReleaseChartsResponse,
  ReleaseListResponse,
  ReleaseMetricsResponse,
  ReleaseSignalResponse,
  RecomputeSprintMetricsResponse,
  Sprint,
  SprintIssueListResponse,
  SprintListResponse,
  SprintMetricsResponse,
  SnapshotBaseline,
  SnapshotChangeHistoryResponse,
  SnapshotComparisonResponse,
  SyncJiraResponse,
} from "./types";
import {
  ApiAuthenticationError,
  reportApiAuthenticationFailure,
  withBrowserApiToken,
} from "./auth";

function getApiBaseUrl() {
  if (import.meta.env.VITE_API_BASE_URL) {
    return import.meta.env.VITE_API_BASE_URL;
  }
  if (window.lighthouseDesktop?.isElectron) {
    return "/api";
  }
  return "http://localhost:8000";
}

const API_BASE_URL = getApiBaseUrl().replace(/\/$/, "");

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const url = `${API_BASE_URL}${path}`;
  let response: Response;

  try {
    response = await fetch(url, withBrowserApiToken(options));
  } catch (error) {
    const method = options?.method ?? "GET";
    const reason = error instanceof Error ? error.message : "Network request failed";
    throw new Error(`Could not reach API (${method} ${url}). Check that the backend is running and CORS allows this UI origin. ${reason}`);
  }

  if (response.status === 401) {
    reportApiAuthenticationFailure();
    throw new ApiAuthenticationError();
  }
  if (!response.ok) {
    const fallback = `Request failed with status ${response.status}`;
    let detail = fallback;
    try {
      const payload = (await response.json()) as { detail?: string };
      detail = payload.detail || fallback;
    } catch {
      detail = fallback;
    }
    throw new Error(detail);
  }

  return (await response.json()) as T;
}

async function requestBlob(path: string, options?: RequestInit): Promise<Blob> {
  const url = `${API_BASE_URL}${path}`;
  let response: Response;

  try {
    response = await fetch(url, withBrowserApiToken(options));
  } catch (error) {
    const method = options?.method ?? "GET";
    const reason = error instanceof Error ? error.message : "Network request failed";
    throw new Error(`Could not reach API (${method} ${url}). Check that the backend is running and CORS allows this UI origin. ${reason}`);
  }

  if (response.status === 401) {
    reportApiAuthenticationFailure();
    throw new ApiAuthenticationError();
  }
  if (!response.ok) {
    const fallback = `Request failed with status ${response.status}`;
    let detail = fallback;
    try {
      const payload = (await response.json()) as { detail?: string };
      detail = payload.detail || fallback;
    } catch {
      detail = fallback;
    }
    throw new Error(detail);
  }

  return response.blob();
}

export const apiClient = {
  getMetricCatalog(): Promise<MetricCatalogResponse> {
    return request<MetricCatalogResponse>("/metadata/metrics");
  },
  getReleases(projectKey?: string | null): Promise<ReleaseListResponse> {
    const params = new URLSearchParams();
    if (projectKey) {
      params.set("project_key", projectKey);
    }
    const query = params.toString();
    return request<ReleaseListResponse>(`/releases${query ? `?${query}` : ""}`);
  },
  getRelease(releaseId: string): Promise<Release> {
    return request<Release>(`/releases/${releaseId}`);
  },
  getReleaseIssues(releaseId: string, skip = 0, limit = 50): Promise<IssueListResponse> {
    return request<IssueListResponse>(`/releases/${releaseId}/issues?skip=${skip}&limit=${limit}`);
  },
  getClosedSprints(projectKey?: string | null): Promise<SprintListResponse> {
    const params = new URLSearchParams({ state: "closed", limit: "100" });
    if (projectKey) {
      params.set("project_key", projectKey);
    }
    return request<SprintListResponse>(`/sprints?${params.toString()}`);
  },
  getCurrentSprint(projectKey?: string | null): Promise<CurrentSprintResponse> {
    const params = new URLSearchParams();
    if (projectKey) {
      params.set("project_key", projectKey);
    }
    const query = params.toString();
    return request<CurrentSprintResponse>(`/sprints/current${query ? `?${query}` : ""}`);
  },
  getSprintIssues(sprintId: string, skip = 0, limit = 50): Promise<SprintIssueListResponse> {
    return request<SprintIssueListResponse>(`/sprints/${sprintId}/issues?skip=${skip}&limit=${limit}`);
  },
  getSprintMetrics(sprintId: string): Promise<SprintMetricsResponse> {
    return request<SprintMetricsResponse>(`/sprints/${sprintId}/metrics`);
  },
  downloadSprintReport(sprintId: string, depth: ReportDepth): Promise<Blob> {
    return requestBlob(`/sprints/${sprintId}/reports/${depth}.pdf`);
  },
  getSprintSnapshotComparison(sprintId: string, baseline: SnapshotBaseline): Promise<SnapshotComparisonResponse> {
    return request<SnapshotComparisonResponse>(`/sprints/${sprintId}/snapshot-comparison?baseline=${baseline}`);
  },
  getSprintSnapshotChangeHistory(sprintId: string): Promise<SnapshotChangeHistoryResponse> {
    return request<SnapshotChangeHistoryResponse>(`/sprints/${sprintId}/snapshot-change-history`);
  },
  recomputeSprint(sprintId: string): Promise<RecomputeSprintMetricsResponse> {
    return request<RecomputeSprintMetricsResponse>(`/sprints/${sprintId}/recompute`, { method: "POST" });
  },
  getIssue(jiraKey: string): Promise<Issue> {
    return request<Issue>(`/issues/${jiraKey}`);
  },
  getMetrics(releaseId: string): Promise<ReleaseMetricsResponse> {
    return request<ReleaseMetricsResponse>(`/releases/${releaseId}/metrics`);
  },
  getCharts(releaseId: string): Promise<ReleaseChartsResponse> {
    return request<ReleaseChartsResponse>(`/releases/${releaseId}/charts?limit=30`);
  },
  getReleaseSnapshotComparison(releaseId: string, baseline: SnapshotBaseline): Promise<SnapshotComparisonResponse> {
    return request<SnapshotComparisonResponse>(`/releases/${releaseId}/snapshot-comparison?baseline=${baseline}`);
  },
  getReleaseSnapshotChangeHistory(releaseId: string): Promise<SnapshotChangeHistoryResponse> {
    return request<SnapshotChangeHistoryResponse>(`/releases/${releaseId}/snapshot-change-history`);
  },
  getSignal(releaseId: string): Promise<ReleaseSignalResponse> {
    return request<ReleaseSignalResponse>(`/releases/${releaseId}/signal`);
  },
  downloadReleaseReport(releaseId: string, depth: ReportDepth): Promise<Blob> {
    return requestBlob(`/releases/${releaseId}/reports/${depth}.pdf`);
  },
  downloadOverviewReport(releaseId: string): Promise<Blob> {
    return requestBlob(`/releases/${releaseId}/reports/overview.pdf`);
  },
  downloadDocumentationReport(): Promise<Blob> {
    return requestBlob("/reports/documentation.pdf");
  },
  recomputeRelease(releaseId: string): Promise<RecomputeMetricsResponse> {
    return request<RecomputeMetricsResponse>(`/releases/${releaseId}/recompute`, { method: "POST" });
  },
  recomputeAllSnapshots(): Promise<RecomputeAllMetricsResponse> {
    return request<RecomputeAllMetricsResponse>("/releases/recompute-all", { method: "POST" });
  },
  getAdminStatus(): Promise<AdminStatusResponse> {
    return request<AdminStatusResponse>("/admin/status");
  },
  syncJira(mode: "incremental" | "full" = "incremental"): Promise<SyncJiraResponse> {
    return request<SyncJiraResponse>(`/sync/jira?mode=${mode}`, { method: "POST" });
  },
  getHealth(): Promise<HealthResponse> {
    return request<HealthResponse>("/health");
  },
  getJiraConfiguration(): Promise<JiraConfigurationResponse> {
    return request<JiraConfigurationResponse>("/config/jira");
  },
  updateJiraConfiguration(update: JiraConfigurationUpdate): Promise<JiraConfigurationResponse> {
    return request<JiraConfigurationResponse>("/config/jira", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(update),
    });
  },
  testJiraConfiguration(update: JiraConfigurationUpdate): Promise<JiraConnectionTestResponse> {
    return request<JiraConnectionTestResponse>("/config/jira/test", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(update),
    });
  },
};
