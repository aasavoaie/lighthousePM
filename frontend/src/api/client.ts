import type {
  RecomputeAllMetricsResponse,
  RecomputeMetricsResponse,
  Release,
  ReleaseChartsResponse,
  ReleaseListResponse,
  ReleaseMetricsResponse,
  ReleaseSignalResponse,
} from "./types";

const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || "http://localhost:8000").replace(/\/$/, "");

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, options);

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
  getMetrics(releaseId: string): Promise<ReleaseMetricsResponse> {
    return request<ReleaseMetricsResponse>(`/releases/${releaseId}/metrics`);
  },
  getCharts(releaseId: string): Promise<ReleaseChartsResponse> {
    return request<ReleaseChartsResponse>(`/releases/${releaseId}/charts?limit=30`);
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
};