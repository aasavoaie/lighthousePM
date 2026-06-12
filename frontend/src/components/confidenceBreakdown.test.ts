import {
  confidenceBreakdownStatusLabels,
  formatConfidenceBreakdownScore,
} from "./confidenceBreakdown";

function assertEqual<T>(actual: T, expected: T, message: string) {
  if (actual !== expected) {
    throw new Error(`${message}: expected ${String(expected)}, received ${String(actual)}`);
  }
}

assertEqual(formatConfidenceBreakdownScore(94, 100), "94%", "percent scores render as percentages");
assertEqual(formatConfidenceBreakdownScore(25, 30), "25/30", "weighted release scores render with max score");
assertEqual(confidenceBreakdownStatusLabels.good, "Good", "good status label is stable");
assertEqual(confidenceBreakdownStatusLabels.warning, "Warning", "warning status label is stable");
assertEqual(confidenceBreakdownStatusLabels.critical, "Critical", "critical status label is stable");
