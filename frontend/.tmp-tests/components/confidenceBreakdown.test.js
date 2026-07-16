"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
const confidenceBreakdown_1 = require("./confidenceBreakdown");
function assertEqual(actual, expected, message) {
    if (actual !== expected) {
        throw new Error(`${message}: expected ${String(expected)}, received ${String(actual)}`);
    }
}
assertEqual((0, confidenceBreakdown_1.formatConfidenceBreakdownScore)(94, 100), "94%", "percent scores render as percentages");
assertEqual((0, confidenceBreakdown_1.formatConfidenceBreakdownScore)(25, 30), "25/30", "weighted release scores render with max score");
assertEqual(confidenceBreakdown_1.confidenceBreakdownStatusLabels.good, "Good", "good status label is stable");
assertEqual(confidenceBreakdown_1.confidenceBreakdownStatusLabels.warning, "Warning", "warning status label is stable");
assertEqual(confidenceBreakdown_1.confidenceBreakdownStatusLabels.critical, "Critical", "critical status label is stable");
