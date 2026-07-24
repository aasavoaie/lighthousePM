import type { ReactNode } from "react";

import {
  APP_TAB_CONTENT,
  isReleaseWorkspaceTab,
  shouldShowWorkspaceHeader,
  type AppTab,
} from "../appNavigation";

type WorkspaceHeaderProps = {
  tab: AppTab;
  isNavigationLocked: boolean;
  releaseTools?: ReactNode;
};

export function WorkspaceHeader({ tab, isNavigationLocked, releaseTools = null }: WorkspaceHeaderProps) {
  if (!shouldShowWorkspaceHeader(tab)) {
    return null;
  }

  const content = APP_TAB_CONTENT[tab];
  return (
    <header className="workspace-header">
      <div>
        <h1>{content.title}</h1>
        <p>{content.subtitle}</p>
        {isNavigationLocked ? (
          <p className="workspace-lock-message">Jira sync is running. Navigation is locked until it finishes.</p>
        ) : null}
      </div>
      {isReleaseWorkspaceTab(tab) ? releaseTools : null}
    </header>
  );
}
