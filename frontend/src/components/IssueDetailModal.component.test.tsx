import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe } from "jest-axe";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { apiClient } from "../api/client";
import type { Issue } from "../api/types";
import { IssueDetailModal } from "./IssueDetailModal";

vi.mock("../api/client", () => ({ apiClient: { getIssue: vi.fn() } }));

function issue(): Issue {
  return {
    issue_key: "ALPHA-1",
    summary: "Accessible issue details",
    issue_type: "Story",
    status: "In Progress",
    priority: "Medium",
    assignee: "Ava",
    story_points: 3,
    release_id: "REL-1",
    is_blocker: false,
    jira_created_at: "2026-07-01T00:00:00Z",
    jira_updated_at: "2026-07-02T00:00:00Z",
    created_at: "2026-07-01T00:00:00Z",
    updated_at: "2026-07-02T00:00:00Z",
  };
}

const getIssue = vi.mocked(apiClient.getIssue);

describe("issue detail dialog", () => {
  beforeEach(() => {
    vi.resetAllMocks();
    getIssue.mockResolvedValue(issue());
  });

  it("has a heading-derived accessible name and renders issue details", async () => {
    const { container } = render(<IssueDetailModal issueKey="ALPHA-1" onClose={() => {}} />);

    expect(screen.getByRole("dialog", { name: "Issue ALPHA-1" })).toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent("Loading issue...");
    expect(await screen.findByText("Accessible issue details")).toBeInTheDocument();
    expect((await axe(container)).violations).toEqual([]);
  });

  it("closes through both its named button and the Escape key", async () => {
    const onClose = vi.fn();
    const user = userEvent.setup();
    const { rerender } = render(<IssueDetailModal issueKey="ALPHA-1" onClose={onClose} />);

    await user.click(screen.getByRole("button", { name: "Close" }));
    expect(onClose).toHaveBeenCalledTimes(1);

    const escapeClose = vi.fn();
    rerender(<IssueDetailModal issueKey="ALPHA-1" onClose={escapeClose} />);
    await user.keyboard("{Escape}");
    expect(escapeClose).toHaveBeenCalledTimes(1);
  });

  it("announces issue API failures", async () => {
    getIssue.mockRejectedValue(new Error("Issue API unavailable"));
    render(<IssueDetailModal issueKey="ALPHA-1" onClose={() => {}} />);

    expect(await screen.findByRole("alert")).toHaveTextContent("Issue API unavailable");
    expect(screen.queryByText("Accessible issue details")).not.toBeInTheDocument();
  });
});
