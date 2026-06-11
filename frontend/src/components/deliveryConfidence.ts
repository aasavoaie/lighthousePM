import type { DeliveryConfidenceComponents, DeliveryConfidenceInputs } from "../api/types";

export type ConfidenceComponentKey = keyof DeliveryConfidenceComponents;
export type ConfidenceStatusLevel = "healthy" | "watch" | "risk" | "critical";
export type RiskDriverSeverity = "positive" | "warning" | "critical";

export interface ConfidenceStatus {
  level: ConfidenceStatusLevel;
  label: string;
}

export interface ConfidenceComponentDetail {
  key: ConfidenceComponentKey;
  label: string;
  score: number;
  status: ConfidenceStatus;
  explanation: string;
}

export interface ExpectedVsActualProgress {
  expectedProgress: number | null;
  actualProgress: number | null;
  gap: number | null;
}

export interface RiskDriver {
  message: string;
  severity: RiskDriverSeverity;
}

export const confidenceComponentOrder: ConfidenceComponentKey[] = [
  "progress_alignment",
  "velocity_fit",
  "blocker_penalty",
  "scope_stability",
];

export const confidenceComponentLabels: Record<ConfidenceComponentKey, string> = {
  progress_alignment: "Progress Alignment",
  velocity_fit: "Velocity Fit",
  blocker_penalty: "Blocker Health",
  scope_stability: "Scope Stability",
};

export function roundPercent(value: number) {
  return Math.round(value);
}

export function formatConfidencePercent(value: number) {
  return `${roundPercent(value)}%`;
}

export function getConfidenceStatus(value: number): ConfidenceStatus {
  if (value >= 80) {
    return { level: "healthy", label: "Healthy" };
  }
  if (value >= 60) {
    return { level: "watch", label: "Watch" };
  }
  if (value >= 40) {
    return { level: "risk", label: "Moderate Risk" };
  }
  return { level: "critical", label: "High Risk" };
}

export function getComponentStatus(value: number): ConfidenceStatus {
  if (value >= 80) {
    return { level: "healthy", label: "Healthy" };
  }
  if (value >= 60) {
    return { level: "watch", label: "Watch" };
  }
  if (value >= 40) {
    return { level: "risk", label: "Risk" };
  }
  return { level: "critical", label: "Critical" };
}

export function getComponentExplanation(key: ConfidenceComponentKey, value: number) {
  if (key === "progress_alignment") {
    if (value >= 80) {
      return "Actual progress is aligned with expected sprint progress.";
    }
    if (value >= 60) {
      return "Actual progress is close to expected sprint progress.";
    }
    return "Actual progress is behind expected sprint progress.";
  }

  if (key === "velocity_fit") {
    if (value >= 80) {
      return "Current pace is supported by historical velocity.";
    }
    if (value >= 60) {
      return "Current pace is near historical velocity.";
    }
    return "Current pace is below historical velocity.";
  }

  if (key === "blocker_penalty") {
    if (value >= 80) {
      return "Blocked work is not materially affecting delivery confidence.";
    }
    if (value >= 60) {
      return "Blocked work needs monitoring.";
    }
    return "Blocked work is reducing delivery confidence.";
  }

  if (value >= 80) {
    return "Sprint scope has remained stable.";
  }
  if (value >= 60) {
    return "Scope changes are manageable.";
  }
  return "Scope changed significantly after sprint start.";
}

export function getConfidenceComponentDetails(
  components: DeliveryConfidenceComponents
): ConfidenceComponentDetail[] {
  return confidenceComponentOrder.map((key) => {
    const score = components[key];
    return {
      key,
      label: confidenceComponentLabels[key],
      score,
      status: getComponentStatus(score),
      explanation: getComponentExplanation(key, score),
    };
  });
}

export function getBiggestDrag(components: DeliveryConfidenceComponents): ConfidenceComponentDetail {
  const [lowest] = getConfidenceComponentDetails(components).sort(
    (left, right) =>
      left.score - right.score ||
      confidenceComponentOrder.indexOf(left.key) - confidenceComponentOrder.indexOf(right.key)
  );
  return lowest;
}

export function calculateExpectedVsActualProgress(inputs: DeliveryConfidenceInputs): ExpectedVsActualProgress {
  const expectedProgress = inputs.time_elapsed_pct;
  const actualProgress =
    inputs.committed_effective_points > 0
      ? (inputs.completed_effective_points / inputs.committed_effective_points) * 100
      : null;

  return {
    expectedProgress,
    actualProgress,
    gap: expectedProgress !== null && actualProgress !== null ? actualProgress - expectedProgress : null,
  };
}

export function getRiskDrivers(components: DeliveryConfidenceComponents): RiskDriver[] {
  const drivers: RiskDriver[] = [];

  if (components.progress_alignment < 60) {
    drivers.push({
      message: "Progress is behind expected sprint pace.",
      severity: components.progress_alignment < 40 ? "critical" : "warning",
    });
  }
  if (components.velocity_fit < 60) {
    drivers.push({
      message: "Current pace is below historical velocity.",
      severity: components.velocity_fit < 40 ? "critical" : "warning",
    });
  }
  if (components.scope_stability < 60) {
    drivers.push({
      message: "Scope changed significantly after sprint start.",
      severity: components.scope_stability < 40 ? "critical" : "warning",
    });
  }
  if (components.blocker_penalty < 60) {
    drivers.push({
      message: "Blocked work is reducing delivery confidence.",
      severity: components.blocker_penalty < 40 ? "critical" : "warning",
    });
  }

  if (drivers.length === 0 && getConfidenceComponentDetails(components).every((detail) => detail.score >= 80)) {
    return [{ message: "No major delivery confidence risks detected.", severity: "positive" }];
  }

  return drivers;
}

function formatComponentList(labels: string[]) {
  if (labels.length === 0) {
    return "";
  }
  if (labels.length === 1) {
    return labels[0];
  }
  return `${labels.slice(0, -1).join(", ")} and ${labels[labels.length - 1]}`;
}

function capitalizeFirst(value: string) {
  return value.length === 0 ? value : `${value[0].toUpperCase()}${value.slice(1)}`;
}

function getPrimarySummarySentence(key: ConfidenceComponentKey, value: number) {
  if (key === "progress_alignment") {
    return value < 60
      ? "Sprint is behind the expected delivery pace."
      : "Sprint progress is tracking close to the expected delivery pace.";
  }
  if (key === "velocity_fit") {
    return value < 60
      ? "Sprint pace is below the historical delivery baseline."
      : "Sprint pace is tracking close to historical velocity.";
  }
  if (key === "blocker_penalty") {
    return value < 60
      ? "Blocked work is weighing on delivery confidence."
      : "Blocker health is not the main delivery constraint.";
  }
  return value < 60
    ? "Scope movement is weighing on delivery confidence."
    : "Scope stability is not the main delivery constraint.";
}

export function getDeliveryConfidenceSummary(components: DeliveryConfidenceComponents) {
  const details = getConfidenceComponentDetails(components);
  if (details.every((detail) => detail.score >= 80)) {
    return "Delivery confidence is healthy across progress, velocity, blocker health, and scope stability.";
  }

  const sorted = [...details].sort(
    (left, right) =>
      left.score - right.score ||
      confidenceComponentOrder.indexOf(left.key) - confidenceComponentOrder.indexOf(right.key)
  );
  const primary = sorted[0];
  const drivers = sorted
    .filter((detail) => detail.score < 80)
    .slice(0, 2)
    .map((detail) => detail.label.toLowerCase());
  const healthyNotes = details
    .filter((detail) => detail.score >= 80)
    .map((detail) => detail.label.toLowerCase());

  const driverSentence = drivers.length > 0
    ? `The main confidence drivers are ${formatComponentList(drivers)}.`
    : "";
  const healthySentence = healthyNotes.length > 0
    ? ` ${capitalizeFirst(formatComponentList(healthyNotes))} ${healthyNotes.length === 1 ? "remains" : "remain"} positive.`
    : "";

  return `${getPrimarySummarySentence(primary.key, primary.score)} ${driverSentence}${healthySentence}`.trim();
}
