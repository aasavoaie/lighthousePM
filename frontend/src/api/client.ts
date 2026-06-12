import type {
  AdminStatusResponse,
  CurrentSprintResponse,
  HealthResponse,
  Issue,
  IssueListResponse,
  RecomputeAllMetricsResponse,
  RecomputeMetricsResponse,
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

const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || "http://localhost:8000").replace(/\/$/, "");

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const url = `${API_BASE_URL}${path}`;
  let response: Response;

  try {
    response = await fetch(url, options);
  } catch (error) {
    const method = options?.method ?? "GET";
    const reason = error instanceof Error ? error.message : "Network request failed";
    throw new Error(`Could not reach API (${method} ${url}). Check that the backend is running and CORS allows this UI origin. ${reason}`);
  }

  if (!response.ok) {
    const fallback = `Request failed with status ${response.status}`;
    try {
      const payload = (await response.json()) as { detail?: string };
      throw new Error(payload.detail || fallback);
    } catch {
      throw new Error(fallback);
    }
  }

  return (await response.json()) as T;
}

export const apiClient = {
  getReleases(): Promise<ReleaseListResponse> {
    return request<ReleaseListResponse>("/releases");
  },
  getRelease(releaseId: string): Promise<Release> {
    return request<Release>(`/releases/${releaseId}`);
  },
  getReleaseIssues(releaseId: string, skip = 0, limit = 50): Promise<IssueListResponse> {
    return request<IssueListResponse>(`/releases/${releaseId}/issues?skip=${skip}&limit=${limit}`);
  },
  getClosedSprints(): Promise<SprintListResponse> {
    return request<SprintListResponse>("/sprints?state=closed&limit=100");
  },
  getCurrentSprint(): Promise<CurrentSprintResponse> {
    return request<CurrentSprintResponse>("/sprints/current");
  },
  getSprintIssues(sprintId: string, skip = 0, limit = 50): Promise<SprintIssueListResponse> {
    return request<SprintIssueListResponse>(`/sprints/${sprintId}/issues?skip=${skip}&limit=${limit}`);
  },
  getSprintMetrics(sprintId: string): Promise<SprintMetricsResponse> {
    return request<SprintMetricsResponse>(`/sprints/${sprintId}/metrics`);
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
  recomputeRelease(releaseId: string): Promise<RecomputeMetricsResponse> {
    return request<RecomputeMetricsResponse>(`/releases/${releaseId}/recompute`, { method: "POST" });
  },
  recomputeAllSnapshots(): Promise<RecomputeAllMetricsResponse> {
    return request<RecomputeAllMetricsResponse>("/releases/recompute-all", { method: "POST" });
  },
  getAdminStatus(): Promise<AdminStatusResponse> {
    return request<AdminStatusResponse>("/admin/status");
  },
  syncJira(): Promise<SyncJiraResponse> {
    return request<SyncJiraResponse>("/sync/jira", { method: "POST" });
  },
  getHealth(): Promise<HealthResponse> {
    return request<HealthResponse>("/health");
  },
};
