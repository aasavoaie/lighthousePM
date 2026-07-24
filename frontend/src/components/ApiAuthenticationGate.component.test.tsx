import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe } from "jest-axe";
import { beforeEach, describe, expect, it, vi } from "vitest";

import {
  ApiAuthenticationError,
  clearBrowserApiToken,
  getBrowserApiToken,
  reportApiAuthenticationFailure,
} from "../api/auth";
import { apiClient } from "../api/client";
import type { JiraConfigurationResponse } from "../api/types";
import { ApiAuthenticationGate } from "./ApiAuthenticationGate";

vi.mock("../api/client", () => ({
  apiClient: {
    getJiraConfiguration: vi.fn(),
  },
}));

function configuration(): JiraConfigurationResponse {
  return { is_complete: true } as JiraConfigurationResponse;
}

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((resolvePromise, rejectPromise) => {
    resolve = resolvePromise;
    reject = rejectPromise;
  });
  return { promise, reject, resolve };
}

const getJiraConfiguration = vi.mocked(apiClient.getJiraConfiguration);

describe("ApiAuthenticationGate", () => {
  beforeEach(() => {
    clearBrowserApiToken();
    Object.defineProperty(window, "lighthouseDesktop", {
      configurable: true,
      value: undefined,
      writable: true,
    });
  });

  it("shows an accessible checking state while anonymous access is unresolved", async () => {
    const pending = deferred<JiraConfigurationResponse>();
    getJiraConfiguration.mockReturnValue(pending.promise);

    const { container } = render(
      <ApiAuthenticationGate>
        <p>Authenticated workspace</p>
      </ApiAuthenticationGate>
    );

    expect(screen.getByRole("heading", { name: "Checking API access" })).toBeInTheDocument();
    expect(screen.queryByText("Authenticated workspace")).not.toBeInTheDocument();
    expect((await axe(container)).violations).toEqual([]);

    pending.resolve(configuration());
    expect(await screen.findByText("Authenticated workspace")).toBeInTheDocument();
  });

  it("associates empty and invalid-token errors with the token field", async () => {
    getJiraConfiguration
      .mockRejectedValueOnce(new ApiAuthenticationError())
      .mockRejectedValueOnce(new ApiAuthenticationError());
    const user = userEvent.setup();
    const { container } = render(
      <ApiAuthenticationGate>
        <p>Authenticated workspace</p>
      </ApiAuthenticationGate>
    );

    const tokenInput = await screen.findByLabelText("API token");
    await user.click(screen.getByRole("button", { name: "Continue" }));
    let alert = screen.getByRole("alert");
    expect(alert).toHaveTextContent("Enter the API token supplied by the LighthousePM operator.");
    expect(tokenInput).toHaveAttribute("aria-describedby", alert.id);
    expect(tokenInput).toHaveAttribute("aria-invalid", "true");

    await user.type(tokenInput, "invalid-token");
    await user.click(screen.getByRole("button", { name: "Continue" }));
    alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("The API token is missing or invalid.");
    expect(tokenInput).toHaveValue("");
    expect(getBrowserApiToken()).toBeNull();
    expect((await axe(container)).violations).toEqual([]);
  });

  it("disables token controls while validating and renders children after success", async () => {
    const validation = deferred<JiraConfigurationResponse>();
    getJiraConfiguration
      .mockRejectedValueOnce(new ApiAuthenticationError())
      .mockReturnValueOnce(validation.promise);
    const user = userEvent.setup();
    render(
      <ApiAuthenticationGate>
        <p>Authenticated workspace</p>
      </ApiAuthenticationGate>
    );

    const tokenInput = await screen.findByLabelText("API token");
    await user.type(tokenInput, "valid-token");
    await user.click(screen.getByRole("button", { name: "Continue" }));

    expect(screen.getByRole("button", { name: "Checking..." })).toBeDisabled();
    expect(tokenInput).toBeDisabled();
    validation.resolve(configuration());
    expect(await screen.findByText("Authenticated workspace")).toBeInTheDocument();
  });

  it("lets the workspace display ordinary API connectivity failures", async () => {
    getJiraConfiguration.mockRejectedValue(new Error("Backend unavailable"));

    render(
      <ApiAuthenticationGate>
        <p>Authenticated workspace</p>
      </ApiAuthenticationGate>
    );

    expect(await screen.findByText("Authenticated workspace")).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "API token required" })).not.toBeInTheDocument();
  });

  it("returns an authenticated workspace to a cleared token form after a later 401", async () => {
    getJiraConfiguration.mockResolvedValue(configuration());
    render(
      <ApiAuthenticationGate>
        <p>Authenticated workspace</p>
      </ApiAuthenticationGate>
    );
    expect(await screen.findByText("Authenticated workspace")).toBeInTheDocument();

    act(() => reportApiAuthenticationFailure());

    expect(await screen.findByRole("heading", { name: "API token required" })).toBeInTheDocument();
    expect(screen.getByLabelText("API token")).toHaveValue("");
    expect(screen.getByRole("alert")).toHaveTextContent("The API token is missing or invalid.");
    await waitFor(() => expect(getBrowserApiToken()).toBeNull());
  });
});
