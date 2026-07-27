import { render, screen } from "@testing-library/react";
import { axe } from "jest-axe";
import { describe, expect, it } from "vitest";

import { AboutKnowledgePanel } from "./AboutKnowledgePanel";


describe("About knowledge content", () => {
  it("uses catalog-backed release metric labels and current event semantics", async () => {
    const { container } = render(<AboutKnowledgePanel page="releases" />);

    expect(
      screen.getByRole("heading", { name: "Metric: Scope churn 7d" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { name: "Metric: Scope added 7d" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { name: "Metric: Scope removed 7d" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { name: "Metric: Release confidence" }),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/Every distinct transition is counted/),
    ).toHaveTextContent("may exceed 100%");
    expect(screen.queryByRole("heading", { name: "Metric: Scope creep" }))
      .not.toBeInTheDocument();
    expect((await axe(container)).violations).toEqual([]);
  });

  it("distinguishes sprint metrics, derived views, and confidence components", () => {
    render(<AboutKnowledgePanel page="sprints" />);

    expect(
      screen.getByRole("heading", { name: "Metric: Workload concentration" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { name: "Metric: Delivery confidence" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("heading", {
        name: "Derived view: Historical commitment reliability",
      }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("heading", {
        name: "Delivery-confidence component: Progress alignment",
      }),
    ).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Metric: Work distribution" }))
      .not.toBeInTheDocument();
  });
});
