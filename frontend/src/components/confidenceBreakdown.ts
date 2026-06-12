import type { ConfidenceBreakdownStatus } from "../api/types";

export const confidenceBreakdownStatusLabels: Record<ConfidenceBreakdownStatus, string> = {
  good: "Good",
  warning: "Warning",
  critical: "Critical",
};

export function formatConfidenceBreakdownScore(score: number, maxScore: number) {
  if (maxScore === 100) {
    return `${Math.round(score)}%`;
  }
  return `${Number(score.toFixed(1))}/${Number(maxScore.toFixed(1))}`;
}
