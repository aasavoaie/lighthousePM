import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe } from "jest-axe";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { apiClient } from "../api/client";
import { ReportExportActions } from "./ReportExportActions";

vi.mock("../api/client", () => ({
  apiClient: {
    downloadOverviewReport: vi.fn(),
    downloadReleaseReport: vi.fn(),
    downloadSprintReport: vi.fn(),
  },
}));

function deferred<T>() {
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((_resolve, rejectPromise) => {
    reject = rejectPromise;
  });
  return { promise, reject };
}

const downloadReleaseReport = vi.mocked(apiClient.downloadReleaseReport);

describe("report export actions", () => {
  beforeEach(() => vi.resetAllMocks());

  it("disables exports without an entity and has no automated accessibility violations", async () => {
    const { container } = render(<ReportExportActions entity="release" entityId={null} filenameLabel="Release" />);

    expect(screen.getByRole("button", { name: "Export Summary PDF" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Export Full Report PDF" })).toBeDisabled();
    expect((await axe(container)).violations).toEqual([]);
  });

  it("disables parallel exports and announces an export failure", async () => {
    const exportRequest = deferred<Blob>();
    downloadReleaseReport.mockReturnValue(exportRequest.promise);
    const user = userEvent.setup();
    render(<ReportExportActions entity="release" entityId="REL-1" filenameLabel="Release One" />);

    await user.click(screen.getByRole("button", { name: "Export Summary PDF" }));
    expect(screen.getByRole("button", { name: "Exporting..." })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Export Full Report PDF" })).toBeDisabled();

    exportRequest.reject(new Error("PDF service unavailable"));
    expect(await screen.findByRole("alert")).toHaveTextContent("PDF service unavailable");
    expect(screen.getByRole("button", { name: "Export Summary PDF" })).toBeEnabled();
  });
});
