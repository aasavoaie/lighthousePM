"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.FOOTER_NAVIGATION = exports.PRIMARY_NAVIGATION = exports.APP_TAB_CONTENT = void 0;
exports.getSprintWorkspaceMode = getSprintWorkspaceMode;
exports.isAboutTab = isAboutTab;
exports.isReleaseWorkspaceTab = isReleaseWorkspaceTab;
exports.shouldShowWorkspaceHeader = shouldShowWorkspaceHeader;
exports.shouldShowDetailHeader = shouldShowDetailHeader;
function getSprintWorkspaceMode(tab) {
    if (tab === "sprint-intelligence") {
        return "intelligence";
    }
    if (tab === "sprint-reports") {
        return "reports";
    }
    return null;
}
function isAboutTab(tab) {
    return tab === "about-overview" || tab === "about-releases" || tab === "about-sprints";
}
function isReleaseWorkspaceTab(tab) {
    return tab === "overview" || tab === "release-command" || tab === "release-reports";
}
function shouldShowWorkspaceHeader(tab) {
    return tab !== "release-reports" && tab !== "sprint-reports";
}
function shouldShowDetailHeader(tab) {
    return tab === "release-reports" || tab === "sprint-reports" || tab === "settings";
}
exports.APP_TAB_CONTENT = {
    overview: {
        title: "Risk & Intelligence Platform",
        subtitle: "Intelligent insights to help you ship with confidence.",
        kicker: "Overview",
    },
    "release-command": {
        title: "Release Command Center",
        subtitle: "Review readiness, metrics, and release tickets in one operational view.",
        kicker: "Release Health",
    },
    "release-reports": {
        title: "Reports & Evidence",
        subtitle: "Inspect confidence history, risk contribution, blocker aging, and ticket detail.",
        kicker: "Release Reports",
    },
    "sprint-intelligence": {
        title: "Sprint Intelligence",
        subtitle: "Track delivery confidence, sprint flow, scope movement, and active work.",
        kicker: "Sprint Health",
    },
    "sprint-reports": {
        title: "Reports & Evidence",
        subtitle: "Inspect sprint confidence history, reliability, scope movement, quality, flow, and risk heatmaps.",
        kicker: "Sprint Reports",
    },
    admin: {
        title: "Operations Console",
        subtitle: "Run Jira ingestion and recompute deterministic snapshots for the workspace.",
        kicker: "Admin",
    },
    settings: {
        title: "Settings",
        subtitle: "Configure Jira sync for the local workspace.",
        kicker: "Configuration",
    },
    "about-overview": {
        title: "Lighthouse PM",
        subtitle: "How the Overview dashboard supports executive release decisions.",
        kicker: "Overview",
    },
    "about-releases": {
        title: "Lighthouse PM",
        subtitle: "How release Command Center and Reports views support release governance.",
        kicker: "Releases",
    },
    "about-sprints": {
        title: "Lighthouse PM",
        subtitle: "How sprint intelligence and sprint reports support delivery governance.",
        kicker: "Sprints",
    },
};
exports.PRIMARY_NAVIGATION = [
    { kind: "link", tab: "overview", label: "Overview", iconClass: "nav-overview" },
    {
        kind: "group",
        label: "Releases",
        iconClass: "nav-releases",
        items: [
            { tab: "release-command", label: "Command Center" },
            { tab: "release-reports", label: "Reports & Evidence" },
        ],
    },
    {
        kind: "group",
        label: "Sprints",
        iconClass: "nav-sprints",
        items: [
            { tab: "sprint-intelligence", label: "Sprint Intelligence" },
            { tab: "sprint-reports", label: "Reports & Evidence" },
        ],
    },
    { kind: "link", tab: "admin", label: "Admin", iconClass: "nav-admin" },
];
exports.FOOTER_NAVIGATION = [
    { kind: "link", tab: "settings", label: "Settings", iconClass: "nav-settings", subtle: true },
    {
        kind: "group",
        label: "About",
        iconClass: "nav-help",
        items: [
            { tab: "about-overview", label: "Overview" },
            { tab: "about-releases", label: "Releases" },
            { tab: "about-sprints", label: "Sprints" },
        ],
    },
];
