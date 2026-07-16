"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.MetricStatusCard = MetricStatusCard;
exports.MetricCategorySection = MetricCategorySection;
exports.formatSignedDelta = formatSignedDelta;
exports.getDeltaImpact = getDeltaImpact;
const jsx_runtime_1 = require("react/jsx-runtime");
const statusLabels = {
    good: "Good",
    warning: "Warning",
    critical: "Critical",
    neutral: "Info",
};
function MetricStatusCard({ id, title, value, status, isHighlighted = false, comparison, comparisonImpact = "unknown", details = [], infoText, badge, badgeTitle, children, }) {
    return ((0, jsx_runtime_1.jsxs)("article", { id: id, className: `metric-card metric-status-card metric-status-${status} ${isHighlighted ? "metric-card-highlighted" : ""}`, children: [(0, jsx_runtime_1.jsxs)("div", { className: "metric-status-heading", children: [(0, jsx_runtime_1.jsx)("span", { className: "metric-status-dot", "aria-hidden": "true" }), (0, jsx_runtime_1.jsx)("h3", { children: title }), (0, jsx_runtime_1.jsxs)("div", { className: "metric-status-actions", children: [infoText ? ((0, jsx_runtime_1.jsx)("button", { type: "button", className: "info-button compact-info-button", title: infoText, "aria-label": `${title} info`, children: "i" })) : null, badge ? ((0, jsx_runtime_1.jsx)("span", { className: "metric-muted-badge", title: badgeTitle ?? undefined, children: badge })) : null, (0, jsx_runtime_1.jsx)("span", { className: "metric-status-label", children: statusLabels[status] })] })] }), (0, jsx_runtime_1.jsx)("strong", { children: value }), comparison ? (0, jsx_runtime_1.jsx)("p", { className: `metric-comparison metric-impact-${comparisonImpact}`, children: comparison }) : null, details.length > 0 ? ((0, jsx_runtime_1.jsx)("ul", { className: "metric-detail-list", children: details.map((detail) => ((0, jsx_runtime_1.jsx)("li", { children: detail }, detail))) })) : null, children] }));
}
function MetricCategorySection({ title, summary, children }) {
    return ((0, jsx_runtime_1.jsxs)("div", { className: "metric-category-section", children: [(0, jsx_runtime_1.jsx)("h3", { children: title }), summary ? (0, jsx_runtime_1.jsx)("p", { className: "metric-category-summary", children: summary }) : null, (0, jsx_runtime_1.jsx)("div", { className: "metric-grid", children: children })] }));
}
function formatSignedDelta(delta, formatter) {
    if (delta === 0) {
        return "No change since previous snapshot";
    }
    const sign = delta > 0 ? "+" : "-";
    return `${sign}${formatter(Math.abs(delta))} since previous snapshot`;
}
function getDeltaImpact(delta, direction) {
    if (delta === null || delta === 0 || direction === "neutral") {
        return "neutral";
    }
    if (direction === "higher-is-better") {
        return delta > 0 ? "positive" : "negative";
    }
    return delta < 0 ? "positive" : "negative";
}
