import type {
  Release,
  ReleaseChartsResponse,
  ReleaseMetricsResponse,
  ReleaseSignalResponse,
} from "../api/types";
import { ChartsPanel } from "../components/ChartsPanel";
import { IssuesPanel } from "../components/IssuesPanel";

type ReleaseReportsPageProps = {
  releases: Release[];
  selectedProjectKey: string | null;
  selectedReleaseId: string;
  selectedRelease: Release | null;
  metrics: ReleaseMetricsResponse | null;
  charts: ReleaseChartsResponse | null;
  signal: ReleaseSignalResponse | null;
  refreshNonce: number;
  isLoading: boolean;
  onSelectIssue: (issueKey: string) => void;
};

export function ReleaseReportsPage({
  releases,
  selectedProjectKey,
  selectedReleaseId,
  selectedRelease,
  metrics,
  charts,
  signal,
  refreshNonce,
  isLoading,
  onSelectIssue,
}: ReleaseReportsPageProps) {
  return (
    <>
      <ChartsPanel
        charts={charts}
        signal={signal}
        metrics={metrics}
        releases={releases}
        selectedProjectKey={selectedProjectKey}
        selectedReleaseName={selectedRelease?.name ?? null}
        refreshNonce={refreshNonce}
        isLoading={isLoading}
      />
      <IssuesPanel releaseId={selectedReleaseId} refreshNonce={refreshNonce} onSelectIssue={onSelectIssue} />
    </>
  );
}
