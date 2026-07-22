import type { ReactNode } from "react";

import type { Release } from "../api/types";
import { APP_TAB_CONTENT, type AppTab } from "../appNavigation";

type DetailHeaderProps = {
  tab: AppTab;
  selectedRelease: Release | null;
  releaseTools?: ReactNode;
};

export function DetailHeader({ tab, selectedRelease, releaseTools = null }: DetailHeaderProps) {
  const content = APP_TAB_CONTENT[tab];
  const isReleaseTab = tab === "release-reports";

  return (
    <section className="detail-hero">
      <div>
        <p className="detail-hero-kicker">{content.kicker}</p>
        <h2>{content.title}</h2>
        <p>{content.subtitle}</p>
      </div>
      {isReleaseTab ? (
        <div className="detail-hero-side">
          {releaseTools}
          {selectedRelease ? (
            <dl className="detail-release-meta" aria-label="Selected release summary">
              <div>
                <dt>Project</dt>
                <dd>{selectedRelease.project_key}</dd>
              </div>
              <div>
                <dt>Status</dt>
                <dd>{selectedRelease.status ?? "Unknown"}</dd>
              </div>
              <div>
                <dt>Release</dt>
                <dd>{selectedRelease.release_date ? new Date(selectedRelease.release_date).toLocaleDateString() : "N/A"}</dd>
              </div>
            </dl>
          ) : null}
        </div>
      ) : null}
    </section>
  );
}
