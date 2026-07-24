import {
  APP_TAB_CONTENT,
  FOOTER_NAVIGATION,
  getSprintWorkspaceMode,
  isAboutTab,
  isReleaseWorkspaceTab,
  PRIMARY_NAVIGATION,
  shouldShowDetailHeader,
  shouldShowWorkspaceHeader,
  type AppTab,
  type NavigationItem,
} from "./appNavigation";

function assert(condition: boolean, message: string) {
  if (!condition) {
    throw new Error(message);
  }
}

function assertEqual<T>(actual: T, expected: T, message: string) {
  if (actual !== expected) {
    throw new Error(`${message}: expected ${String(expected)}, received ${String(actual)}`);
  }
}

function tabsFrom(items: ReadonlyArray<NavigationItem>): AppTab[] {
  return items.flatMap((item) =>
    item.kind === "link" ? [item.tab] : item.items.map((subItem) => subItem.tab)
  );
}

const configuredTabs = [...tabsFrom(PRIMARY_NAVIGATION), ...tabsFrom(FOOTER_NAVIGATION)];
const contentTabs = Object.keys(APP_TAB_CONTENT) as AppTab[];

assert(configuredTabs.length === 10, "the sidebar should contain every supported application tab");
assert(new Set(configuredTabs).size === configuredTabs.length, "each application tab should appear once in navigation");
assert(
  [...configuredTabs].sort().join("|") === [...contentTabs].sort().join("|"),
  "navigation tabs and workspace-header content should stay synchronized"
);

for (const tab of configuredTabs) {
  const content = APP_TAB_CONTENT[tab];
  assert(Boolean(content.title.trim()), `${tab} should have a title`);
  assert(Boolean(content.subtitle.trim()), `${tab} should have a subtitle`);
  assert(Boolean(content.kicker.trim()), `${tab} should have a kicker`);
}

assertEqual(
  getSprintWorkspaceMode("sprint-intelligence"),
  "intelligence",
  "the sprint intelligence tab should use the shared intelligence mode"
);
assertEqual(
  getSprintWorkspaceMode("sprint-reports"),
  "reports",
  "the sprint reports tab should use the shared reports mode"
);
assertEqual(getSprintWorkspaceMode("overview"), null, "non-sprint tabs should not mount the sprint workspace");
assertEqual(isReleaseWorkspaceTab("overview"), true, "overview should use release workspace controls");
assertEqual(isReleaseWorkspaceTab("release-command"), true, "command center should use release workspace controls");
assertEqual(isReleaseWorkspaceTab("release-reports"), true, "release reports should use release workspace controls");
assertEqual(isReleaseWorkspaceTab("sprint-reports"), false, "sprint reports should not use release workspace controls");
assertEqual(isAboutTab("about-sprints"), true, "About sprint documentation should be recognized as About content");
assertEqual(isAboutTab("settings"), false, "Settings should not be recognized as About content");
assertEqual(shouldShowWorkspaceHeader("overview"), true, "overview should show the workspace header");
assertEqual(shouldShowWorkspaceHeader("release-reports"), false, "release reports should use its detail header");
assertEqual(shouldShowWorkspaceHeader("sprint-reports"), false, "sprint reports should use its detail header");
assertEqual(shouldShowDetailHeader("release-reports"), true, "release reports should show a detail header");
assertEqual(shouldShowDetailHeader("sprint-reports"), true, "sprint reports should show a detail header");
assertEqual(shouldShowDetailHeader("settings"), true, "Settings should preserve its existing detail header");
assertEqual(shouldShowDetailHeader("about-overview"), false, "About pages should not show a detail header");
