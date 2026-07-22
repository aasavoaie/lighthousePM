"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
const appNavigation_1 = require("./appNavigation");
function assert(condition, message) {
    if (!condition) {
        throw new Error(message);
    }
}
function assertEqual(actual, expected, message) {
    if (actual !== expected) {
        throw new Error(`${message}: expected ${String(expected)}, received ${String(actual)}`);
    }
}
function tabsFrom(items) {
    return items.flatMap((item) => item.kind === "link" ? [item.tab] : item.items.map((subItem) => subItem.tab));
}
const configuredTabs = [...tabsFrom(appNavigation_1.PRIMARY_NAVIGATION), ...tabsFrom(appNavigation_1.FOOTER_NAVIGATION)];
const contentTabs = Object.keys(appNavigation_1.APP_TAB_CONTENT);
assert(configuredTabs.length === 10, "the sidebar should contain every supported application tab");
assert(new Set(configuredTabs).size === configuredTabs.length, "each application tab should appear once in navigation");
assert([...configuredTabs].sort().join("|") === [...contentTabs].sort().join("|"), "navigation tabs and workspace-header content should stay synchronized");
for (const tab of configuredTabs) {
    const content = appNavigation_1.APP_TAB_CONTENT[tab];
    assert(Boolean(content.title.trim()), `${tab} should have a title`);
    assert(Boolean(content.subtitle.trim()), `${tab} should have a subtitle`);
    assert(Boolean(content.kicker.trim()), `${tab} should have a kicker`);
}
assertEqual((0, appNavigation_1.getSprintWorkspaceMode)("sprint-intelligence"), "intelligence", "the sprint intelligence tab should use the shared intelligence mode");
assertEqual((0, appNavigation_1.getSprintWorkspaceMode)("sprint-reports"), "reports", "the sprint reports tab should use the shared reports mode");
assertEqual((0, appNavigation_1.getSprintWorkspaceMode)("overview"), null, "non-sprint tabs should not mount the sprint workspace");
assertEqual((0, appNavigation_1.isReleaseWorkspaceTab)("overview"), true, "overview should use release workspace controls");
assertEqual((0, appNavigation_1.isReleaseWorkspaceTab)("release-command"), true, "command center should use release workspace controls");
assertEqual((0, appNavigation_1.isReleaseWorkspaceTab)("release-reports"), true, "release reports should use release workspace controls");
assertEqual((0, appNavigation_1.isReleaseWorkspaceTab)("sprint-reports"), false, "sprint reports should not use release workspace controls");
assertEqual((0, appNavigation_1.isAboutTab)("about-sprints"), true, "About sprint documentation should be recognized as About content");
assertEqual((0, appNavigation_1.isAboutTab)("settings"), false, "Settings should not be recognized as About content");
assertEqual((0, appNavigation_1.shouldShowWorkspaceHeader)("overview"), true, "overview should show the workspace header");
assertEqual((0, appNavigation_1.shouldShowWorkspaceHeader)("release-reports"), false, "release reports should use its detail header");
assertEqual((0, appNavigation_1.shouldShowWorkspaceHeader)("sprint-reports"), false, "sprint reports should use its detail header");
assertEqual((0, appNavigation_1.shouldShowDetailHeader)("release-reports"), true, "release reports should show a detail header");
assertEqual((0, appNavigation_1.shouldShowDetailHeader)("sprint-reports"), true, "sprint reports should show a detail header");
assertEqual((0, appNavigation_1.shouldShowDetailHeader)("settings"), true, "Settings should preserve its existing detail header");
assertEqual((0, appNavigation_1.shouldShowDetailHeader)("about-overview"), false, "About pages should not show a detail header");
