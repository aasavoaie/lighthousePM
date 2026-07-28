import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe } from "jest-axe";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { apiClient } from "../api/client";
import type { Sprint, SprintIssue, SprintMetricsResponse } from "../api/types";
import { SprintsPanel } from "./SprintsPanel";

vi.mock("../api/client", () => ({
  apiClient: {
    getClosedSprints: vi.fn(),
    getCurrentSprint: vi.fn(),
    getSprintIssues: vi.fn(),
    getSprintMetrics: vi.fn(),
    getSprintSnapshotChangeHistory: vi.fn(),
    getSprintSnapshotComparison: vi.fn(),
    recomputeSprint: vi.fn(),
  },
}));

vi.mock("./SprintDeliveryConfidencePanel", () => ({
  SprintDeliveryConfidencePanel: ({ isLoading, metrics }: { isLoading: boolean; metrics: SprintMetricsResponse | null }) => (
    <section aria-label="Delivery confidence probe">
      {isLoading ? <p>Loading sprint details...</p> : null}
      {metrics ? <p>Delivery metrics: {metrics.sprint_id}</p> : null}
    </section>
  ),
}));

vi.mock("./SprintMetricsPanel", () => ({
  buildBaseMetricEvaluation: (key: string) => ({
    key,
    label: key,
    group: "delivery",
    status: "good",
    value: 0,
    formattedValue: "0",
    focusMessage: key,
  }),
  SprintMetricsPanel: () => null,
}));

vi.mock("./SprintReportExportPanel", () => ({ SprintReportExportPanel: () => null }));
vi.mock("./SprintReportsPanel", () => ({ SprintReportsPanel: () => null }));
vi.mock("./SprintTicketSituationPanel", () => ({
  SprintTicketSituationPanel: ({ issues }: { issues: SprintIssue[] }) => (
    <p>Loaded sprint issues: {issues.map((issue) => issue.issue_key).join(", ") || "none"}</p>
  ),
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

function sprint(sprintId: string, state: string, projectKey = "ALPHA"): Sprint {
  return {
    sprint_id: sprintId,
    name: `Sprint ${sprintId}`,
    state,
    project_key: projectKey,
    board_id: "board-1",
    start_date: "2026-07-01T00:00:00Z",
    end_date: "2026-07-14T00:00:00Z",
    complete_date: state === "closed" ? "2026-07-14T00:00:00Z" : null,
    goal: null,
    created_at: "2026-07-01T00:00:00Z",
    updated_at: "2026-07-01T00:00:00Z",
  };
}

function sprintIssue(issueKey: string): SprintIssue {
  return {
    issue_key: issueKey,
    summary: issueKey,
    issue_type: "Story",
    status: "In Progress",
    priority: null,
    assignee: null,
    story_points: 3,
    release_id: null,
    is_blocker: false,
    jira_created_at: null,
    jira_updated_at: null,
    created_at: "2026-07-01T00:00:00Z",
    updated_at: "2026-07-01T00:00:00Z",
    in_initial_scope: true,
  };
}

function sprintMetrics(sprintId: string): SprintMetricsResponse {
  return {
    sprint_id: sprintId,
    ruleset_version: 1,
    ruleset_label: "Ruleset v1",
    calculation_provenance: {},
    snapshot_at: "2026-07-02T00:00:00Z",
    computation_status: "COMPUTED",
    unavailable_reason: null,
    metrics: {
      committed_scope: 1,
      completed_scope_pct: 50,
      scope_creep_pct: null,
      open_blockers: 0,
      open_high_severity_bugs: 0,
      bugs_created_during_sprint: 0,
      in_progress_count: 1,
      not_started_count: 0,
      rollover_count: 0,
      median_cycle_time_days: null,
      reopen_rate_pct: 0,
      workload_concentration_pct: null,
      delivery_confidence_score: null,
    },
    metric_issue_keys: {
      open_blockers: [],
      open_high_severity_bugs: [],
      bugs_created_during_sprint: [],
      bugs_created_during_sprint_missing_created_at: [],
    },
    metric_names: [],
    metric_availability: {
      context: {
        has_tickets: true,
        has_story_points: false,
        has_completed_tickets: false,
        has_release_scope: false,
        has_sprint_scope: true,
        has_changelog: false,
      },
      metrics: {},
    },
    story_point_coverage: {
      total_ticket_count: 1,
      pointed_ticket_count: 0,
      unpointed_ticket_count: 1,
      coverage_pct: 0,
      unpointed_issue_keys: [`${sprintId}-1`],
    },
    delivery_confidence_status: "INCONCLUSIVE",
    bugs_created_during_sprint_status: "COMPUTED",
    delivery_confidence_explanations: ["Story points are insufficient."],
    delivery_confidence: null,
    scope_movement: null,
    workload_distribution: null,
    confidence_breakdown: null,
    biggest_driver: null,
    recommendations: [],
    is_computed: true,
    snapshot_age_hours: 1,
  };
}

const getClosedSprints = vi.mocked(apiClient.getClosedSprints);
const getCurrentSprint = vi.mocked(apiClient.getCurrentSprint);
const getSprintIssues = vi.mocked(apiClient.getSprintIssues);
const getSprintMetrics = vi.mocked(apiClient.getSprintMetrics);

describe("sprint workspace rendering", () => {
  beforeEach(() => {
    vi.resetAllMocks();
    getSprintMetrics.mockImplementation(async (sprintId) => sprintMetrics(sprintId));
    getSprintIssues.mockImplementation(async (sprintId) => ({
      items: [sprintIssue(`${sprintId}-1`)],
      skip: 0,
      limit: 100,
      total: 1,
    }));
  });

  it("shows list loading and then an accessible empty sprint state", async () => {
    const current = deferred<{ item: Sprint | null }>();
    const closed = deferred<{ items: Sprint[]; skip: number; limit: number; total: number }>();
    getCurrentSprint.mockReturnValue(current.promise);
    getClosedSprints.mockReturnValue(closed.promise);

    const { container } = render(<SprintsPanel refreshNonce={0} onSelectIssue={() => {}} projectKey="ALPHA" />);
    expect(screen.getByRole("status")).toHaveTextContent("Loading sprints...");
    expect(screen.getByLabelText("Select sprint")).toBeDisabled();

    current.resolve({ item: null });
    closed.resolve({ items: [], skip: 0, limit: 50, total: 0 });
    await waitFor(() => expect(screen.queryByRole("status")).not.toBeInTheDocument());
    expect(screen.getByRole("option", { name: "No sprints available" })).toBeInTheDocument();
    expect(screen.getByLabelText("Select sprint")).toBeDisabled();
    expect((await axe(container)).violations).toEqual([]);
  });

  it("loads current and closed sprint selections with their details", async () => {
    const active = sprint("S1", "active");
    const closed = sprint("S2", "closed");
    getCurrentSprint.mockResolvedValue({ item: active });
    getClosedSprints.mockResolvedValue({ items: [closed], skip: 0, limit: 50, total: 1 });
    const user = userEvent.setup();

    render(<SprintsPanel refreshNonce={0} onSelectIssue={() => {}} projectKey="ALPHA" />);
    expect(await screen.findByText("Delivery metrics: S1")).toBeInTheDocument();
    expect(screen.getByText("Loaded sprint issues: S1-1")).toBeInTheDocument();

    await user.selectOptions(screen.getByLabelText("Select sprint"), "S2");
    expect(await screen.findByText("Delivery metrics: S2")).toBeInTheDocument();
    expect(screen.getByText("Loaded sprint issues: S2-1")).toBeInTheDocument();
  });

  it("exposes a current-sprint API failure even when closed sprints load", async () => {
    getCurrentSprint.mockRejectedValue(new Error("Current sprint API unavailable"));
    getClosedSprints.mockResolvedValue({ items: [], skip: 0, limit: 50, total: 0 });

    render(<SprintsPanel refreshNonce={0} onSelectIssue={() => {}} projectKey="ALPHA" />);

    expect(await screen.findByRole("alert")).toHaveTextContent("Current sprint API unavailable");
    expect(screen.getByRole("option", { name: "No sprints available" })).toBeInTheDocument();
    expect(screen.queryByText("Loading sprints...")).not.toBeInTheDocument();
  });

  it("clears old metrics and issues while a new sprint loads and after it fails", async () => {
    const active = sprint("S1", "active");
    const closed = sprint("S2", "closed");
    getCurrentSprint.mockResolvedValue({ item: active });
    getClosedSprints.mockResolvedValue({ items: [closed], skip: 0, limit: 50, total: 1 });
    const user = userEvent.setup();

    render(<SprintsPanel refreshNonce={0} onSelectIssue={() => {}} projectKey="ALPHA" />);
    expect(await screen.findByText("Delivery metrics: S1")).toBeInTheDocument();
    expect(screen.getByText("Loaded sprint issues: S1-1")).toBeInTheDocument();

    const nextMetrics = deferred<SprintMetricsResponse>();
    const nextIssues = deferred<{ items: SprintIssue[]; skip: number; limit: number; total: number }>();
    getSprintMetrics.mockReturnValueOnce(nextMetrics.promise);
    getSprintIssues.mockReturnValueOnce(nextIssues.promise);
    await user.selectOptions(screen.getByLabelText("Select sprint"), "S2");

    expect(await screen.findByText("Loading sprint details...")).toBeInTheDocument();
    expect(screen.queryByText("Delivery metrics: S1")).not.toBeInTheDocument();
    expect(screen.getByText("Loaded sprint issues: none")).toBeInTheDocument();

    nextMetrics.reject(new Error("Sprint detail failed"));
    nextIssues.reject(new Error("Sprint detail failed"));
    expect(await screen.findByRole("alert")).toHaveTextContent("Sprint detail failed");
    await waitFor(() => expect(screen.queryByText("Loading sprint details...")).not.toBeInTheDocument());
    expect(screen.queryByText(/Delivery metrics:/)).not.toBeInTheDocument();
    expect(screen.getByText("Loaded sprint issues: none")).toBeInTheDocument();
  });

  it("ignores a late sprint list from a prior project", async () => {
    const alphaCurrent = deferred<{ item: Sprint | null }>();
    const alphaClosed = deferred<{ items: Sprint[]; skip: number; limit: number; total: number }>();
    const beta = sprint("BETA-S1", "active", "BETA");
    getCurrentSprint.mockImplementation((projectKey) => projectKey === "ALPHA"
      ? alphaCurrent.promise
      : Promise.resolve({ item: beta }));
    getClosedSprints.mockImplementation((projectKey) => projectKey === "ALPHA"
      ? alphaClosed.promise
      : Promise.resolve({ items: [], skip: 0, limit: 50, total: 0 }));

    const { rerender } = render(<SprintsPanel refreshNonce={0} onSelectIssue={() => {}} projectKey="ALPHA" />);
    expect(screen.getByText("Loading sprints...")).toBeInTheDocument();
    rerender(<SprintsPanel refreshNonce={0} onSelectIssue={() => {}} projectKey="BETA" />);

    expect(await screen.findByRole("option", { name: "Current: Sprint BETA-S1" })).toBeInTheDocument();
    await act(async () => {
      alphaCurrent.resolve({ item: sprint("ALPHA-S1", "active") });
      alphaClosed.resolve({ items: [], skip: 0, limit: 50, total: 0 });
    });
    expect(screen.getByLabelText("Select sprint")).toHaveValue("BETA-S1");
    expect(screen.queryByText(/ALPHA-S1/)).not.toBeInTheDocument();
  });

  it("clears sprint artifacts and ignores late details from a prior project", async () => {
    const alpha = sprint("ALPHA-S1", "active");
    const beta = sprint("BETA-S1", "active", "BETA");
    const alphaMetrics = deferred<SprintMetricsResponse>();
    const alphaIssues = deferred<{ items: SprintIssue[]; skip: number; limit: number; total: number }>();
    getCurrentSprint.mockImplementation(async (projectKey) => ({ item: projectKey === "ALPHA" ? alpha : beta }));
    getClosedSprints.mockResolvedValue({ items: [], skip: 0, limit: 50, total: 0 });
    getSprintMetrics.mockImplementation((sprintId) => sprintId === alpha.sprint_id
      ? alphaMetrics.promise
      : Promise.resolve(sprintMetrics(beta.sprint_id)));
    getSprintIssues.mockImplementation((sprintId) => sprintId === alpha.sprint_id
      ? alphaIssues.promise
      : Promise.resolve({ items: [sprintIssue("BETA-1")], skip: 0, limit: 100, total: 1 }));

    const { rerender } = render(<SprintsPanel refreshNonce={0} onSelectIssue={() => {}} projectKey="ALPHA" />);
    expect(await screen.findByText("Loading sprint details...")).toBeInTheDocument();
    rerender(<SprintsPanel refreshNonce={0} onSelectIssue={() => {}} projectKey="BETA" />);

    expect(await screen.findByText("Delivery metrics: BETA-S1")).toBeInTheDocument();
    expect(screen.getByText("Loaded sprint issues: BETA-1")).toBeInTheDocument();
    await act(async () => {
      alphaMetrics.resolve(sprintMetrics(alpha.sprint_id));
      alphaIssues.resolve({ items: [sprintIssue("ALPHA-1")], skip: 0, limit: 100, total: 1 });
    });
    expect(screen.getByLabelText("Select sprint")).toHaveValue("BETA-S1");
    expect(screen.getByText("Delivery metrics: BETA-S1")).toBeInTheDocument();
    expect(screen.queryByText(/ALPHA/)).not.toBeInTheDocument();
  });
});
