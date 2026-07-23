import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe } from "jest-axe";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { apiClient } from "../api/client";
import type {
  JiraConfigurationResponse,
  Release,
  ReleaseChartsResponse,
  ReleaseMetricsResponse,
  ReleaseSignalResponse,
} from "../api/types";
import { ReleaseWorkspaceControls } from "../components/ReleaseWorkspaceControls";
import { useReleaseWorkspace } from "./useReleaseWorkspace";

vi.mock("../api/client", () => ({
  apiClient: {
    getCharts: vi.fn(),
    getJiraConfiguration: vi.fn(),
    getMetrics: vi.fn(),
    getRelease: vi.fn(),
    getReleases: vi.fn(),
    getSignal: vi.fn(),
    recomputeAllSnapshots: vi.fn(),
    recomputeRelease: vi.fn(),
  },
}));

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((resolvePromise, rejectPromise) => {
    resolve = resolvePromise;
    reject = rejectPromise;
  });
  return { promise, reject, resolve };
}

function configuration(projectKey = "ALPHA"): JiraConfigurationResponse {
  return {
    is_complete: true,
    jira_project_key: projectKey,
  } as JiraConfigurationResponse;
}

function release(releaseId: string, projectKey = "ALPHA"): Release {
  return {
    release_id: releaseId,
    name: `${projectKey} ${releaseId}`,
    project_key: projectKey,
    description: null,
    status: "In Progress",
    start_date: "2026-01-01T00:00:00Z",
    release_date: "2027-12-31T00:00:00Z",
    created_at: releaseId === "REL-1" ? "2026-07-02T00:00:00Z" : "2026-07-01T00:00:00Z",
    updated_at: "2026-07-02T00:00:00Z",
  };
}

function metrics(releaseId: string): ReleaseMetricsResponse {
  return { release_id: releaseId } as ReleaseMetricsResponse;
}

function charts(releaseId: string): ReleaseChartsResponse {
  return { release_id: releaseId } as ReleaseChartsResponse;
}

function signal(releaseId: string): ReleaseSignalResponse {
  return { release_id: releaseId } as ReleaseSignalResponse;
}

function WorkspaceHarness() {
  const workspace = useReleaseWorkspace();
  return (
    <main>
      <h1>Release workspace</h1>
      <p>Project: {workspace.activeProjectKey ?? "none"}</p>
      <button type="button" onClick={() => workspace.handleConfigurationSaved(configuration("BETA"))}>
        Save BETA project
      </button>
      <ReleaseWorkspaceControls
        releases={workspace.workspaceReleases}
        selectedReleaseId={workspace.selectedReleaseId}
        isLoading={workspace.isLoadingReleases}
        isNavigationLocked={false}
        onSelectRelease={workspace.setSelectedReleaseId}
        onOpenDetails={() => {}}
      />
      {workspace.isLoadingReleases ? <p role="status">Loading release list...</p> : null}
      {!workspace.isLoadingReleases && workspace.workspaceReleases.length === 0 ? (
        <section><h2>No releases</h2></section>
      ) : null}
      {workspace.isLoadingDetails ? <p role="status">Loading release details...</p> : null}
      {workspace.errorMessage ? <p role="alert">{workspace.errorMessage}</p> : null}
      {workspace.selectedRelease ? <p>Release detail: {workspace.selectedRelease.name}</p> : null}
      {workspace.metrics ? <p>Metrics loaded: {workspace.metrics.release_id}</p> : null}
      {workspace.charts ? <p>Charts loaded: {workspace.charts.release_id}</p> : null}
      {workspace.signal ? <p>Signal loaded: {workspace.signal.release_id}</p> : null}
    </main>
  );
}

const getCharts = vi.mocked(apiClient.getCharts);
const getJiraConfiguration = vi.mocked(apiClient.getJiraConfiguration);
const getMetrics = vi.mocked(apiClient.getMetrics);
const getRelease = vi.mocked(apiClient.getRelease);
const getReleases = vi.mocked(apiClient.getReleases);
const getSignal = vi.mocked(apiClient.getSignal);

describe("release workspace rendering", () => {
  beforeEach(() => {
    vi.resetAllMocks();
    getJiraConfiguration.mockResolvedValue(configuration());
  });

  it("shows list loading and then an accessible empty release state", async () => {
    const releaseList = deferred<{ items: Release[]; skip: number; limit: number; total: number }>();
    getReleases.mockReturnValue(releaseList.promise);

    const { container } = render(<WorkspaceHarness />);
    expect(screen.getByRole("status", { name: "" })).toHaveTextContent("Loading release list...");
    expect(screen.getByLabelText("Release:")).toBeDisabled();

    releaseList.resolve({ items: [], skip: 0, limit: 50, total: 0 });
    expect(await screen.findByRole("heading", { name: "No releases" })).toBeInTheDocument();
    expect(screen.queryByText("Loading release list...")).not.toBeInTheDocument();
    expect(screen.getByLabelText("Release:")).toBeDisabled();
    expect((await axe(container)).violations).toEqual([]);
  });

  it("loads the selected release details, metrics, charts, and signal", async () => {
    const selected = release("REL-1");
    const releaseDetail = deferred<Release>();
    const metricDetail = deferred<ReleaseMetricsResponse>();
    const chartDetail = deferred<ReleaseChartsResponse>();
    const signalDetail = deferred<ReleaseSignalResponse>();
    getReleases.mockResolvedValue({ items: [selected], skip: 0, limit: 50, total: 1 });
    getRelease.mockReturnValue(releaseDetail.promise);
    getMetrics.mockReturnValue(metricDetail.promise);
    getCharts.mockReturnValue(chartDetail.promise);
    getSignal.mockReturnValue(signalDetail.promise);

    render(<WorkspaceHarness />);
    expect(await screen.findByText("Loading release details...")).toBeInTheDocument();
    expect(screen.getByLabelText("Release:")).toHaveValue("REL-1");

    releaseDetail.resolve(selected);
    metricDetail.resolve(metrics("REL-1"));
    chartDetail.resolve(charts("REL-1"));
    signalDetail.resolve(signal("REL-1"));

    expect(await screen.findByText("Release detail: ALPHA REL-1")).toBeInTheDocument();
    expect(screen.getByText("Metrics loaded: REL-1")).toBeInTheDocument();
    expect(screen.getByText("Charts loaded: REL-1")).toBeInTheDocument();
    expect(screen.getByText("Signal loaded: REL-1")).toBeInTheDocument();
    expect(screen.queryByText("Loading release details...")).not.toBeInTheDocument();
  });

  it("removes list loading and exposes an API list failure without stale releases", async () => {
    getReleases.mockRejectedValue(new Error("Release API unavailable"));

    render(<WorkspaceHarness />);

    expect(await screen.findByRole("alert")).toHaveTextContent("Release API unavailable");
    expect(screen.getByRole("heading", { name: "No releases" })).toBeInTheDocument();
    expect(screen.queryByText("Loading release list...")).not.toBeInTheDocument();
  });

  it("clears previous detail data while a new selection loads and after it fails", async () => {
    const first = release("REL-1");
    const second = release("REL-2");
    getReleases.mockResolvedValue({ items: [first, second], skip: 0, limit: 50, total: 2 });
    getRelease.mockResolvedValue(first);
    getMetrics.mockResolvedValue(metrics("REL-1"));
    getCharts.mockResolvedValue(charts("REL-1"));
    getSignal.mockResolvedValue(signal("REL-1"));
    const user = userEvent.setup();

    render(<WorkspaceHarness />);
    expect(await screen.findByText("Metrics loaded: REL-1")).toBeInTheDocument();

    const secondRelease = deferred<Release>();
    const secondMetrics = deferred<ReleaseMetricsResponse>();
    const secondCharts = deferred<ReleaseChartsResponse>();
    const secondSignal = deferred<ReleaseSignalResponse>();
    getRelease.mockReturnValue(secondRelease.promise);
    getMetrics.mockReturnValue(secondMetrics.promise);
    getCharts.mockReturnValue(secondCharts.promise);
    getSignal.mockReturnValue(secondSignal.promise);
    await user.selectOptions(screen.getByLabelText("Release:"), "REL-2");
    expect(await screen.findByText("Loading release details...")).toBeInTheDocument();
    expect(screen.queryByText("Metrics loaded: REL-1")).not.toBeInTheDocument();
    expect(screen.queryByText("Charts loaded: REL-1")).not.toBeInTheDocument();
    expect(screen.queryByText("Signal loaded: REL-1")).not.toBeInTheDocument();

    secondRelease.reject(new Error("Second release failed"));
    secondMetrics.reject(new Error("Second release failed"));
    secondCharts.reject(new Error("Second release failed"));
    secondSignal.reject(new Error("Second release failed"));
    expect(await screen.findByRole("alert")).toHaveTextContent("Second release failed");
    await waitFor(() => {
      expect(screen.queryByText("Loading release details...")).not.toBeInTheDocument();
    });
    expect(screen.queryByText(/Release detail:/)).not.toBeInTheDocument();
    expect(screen.queryByText(/Metrics loaded:/)).not.toBeInTheDocument();
  });

  it("ignores a late release list from the project replaced by configuration", async () => {
    const alphaList = deferred<{ items: Release[]; skip: number; limit: number; total: number }>();
    const beta = release("BETA-1", "BETA");
    getReleases.mockImplementation((projectKey) => projectKey === "ALPHA"
      ? alphaList.promise
      : Promise.resolve({ items: [beta], skip: 0, limit: 50, total: 1 }));
    getRelease.mockResolvedValue(beta);
    getMetrics.mockResolvedValue(metrics(beta.release_id));
    getCharts.mockResolvedValue(charts(beta.release_id));
    getSignal.mockResolvedValue(signal(beta.release_id));
    const user = userEvent.setup();

    render(<WorkspaceHarness />);
    expect(await screen.findByText("Project: ALPHA")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Save BETA project" }));

    expect(await screen.findByText("Project: BETA")).toBeInTheDocument();
    expect(await screen.findByText("Metrics loaded: BETA-1")).toBeInTheDocument();

    await act(async () => {
      alphaList.resolve({ items: [release("ALPHA-1")], skip: 0, limit: 50, total: 1 });
    });
    expect(screen.getByLabelText("Release:")).toHaveValue("BETA-1");
    expect(screen.getByText("Metrics loaded: BETA-1")).toBeInTheDocument();
    expect(screen.queryByText(/ALPHA-1/)).not.toBeInTheDocument();
  });

  it("clears old artifacts and ignores late release details after a project change", async () => {
    const alpha = release("ALPHA-1");
    const beta = release("BETA-1", "BETA");
    const alphaRelease = deferred<Release>();
    const alphaMetrics = deferred<ReleaseMetricsResponse>();
    const alphaCharts = deferred<ReleaseChartsResponse>();
    const alphaSignal = deferred<ReleaseSignalResponse>();
    getReleases.mockImplementation(async (projectKey) => ({
      items: [projectKey === "ALPHA" ? alpha : beta],
      skip: 0,
      limit: 50,
      total: 1,
    }));
    getRelease.mockImplementation((releaseId) => releaseId === alpha.release_id ? alphaRelease.promise : Promise.resolve(beta));
    getMetrics.mockImplementation((releaseId) => releaseId === alpha.release_id ? alphaMetrics.promise : Promise.resolve(metrics(beta.release_id)));
    getCharts.mockImplementation((releaseId) => releaseId === alpha.release_id ? alphaCharts.promise : Promise.resolve(charts(beta.release_id)));
    getSignal.mockImplementation((releaseId) => releaseId === alpha.release_id ? alphaSignal.promise : Promise.resolve(signal(beta.release_id)));
    const user = userEvent.setup();

    render(<WorkspaceHarness />);
    expect(await screen.findByText("Loading release details...")).toBeInTheDocument();
    expect(screen.getByLabelText("Release:")).toHaveValue("ALPHA-1");

    await user.click(screen.getByRole("button", { name: "Save BETA project" }));
    expect(await screen.findByText("Metrics loaded: BETA-1")).toBeInTheDocument();
    expect(screen.getByText("Charts loaded: BETA-1")).toBeInTheDocument();
    expect(screen.getByText("Signal loaded: BETA-1")).toBeInTheDocument();

    await act(async () => {
      alphaRelease.resolve(alpha);
      alphaMetrics.resolve(metrics(alpha.release_id));
      alphaCharts.resolve(charts(alpha.release_id));
      alphaSignal.resolve(signal(alpha.release_id));
    });
    expect(screen.getByLabelText("Release:")).toHaveValue("BETA-1");
    expect(screen.getByText("Release detail: BETA BETA-1")).toBeInTheDocument();
    expect(screen.queryByText(/loaded: ALPHA-1/)).not.toBeInTheDocument();
  });
});
