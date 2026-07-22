import type {
  MetricValues,
  Release,
  ReleaseChartsResponse,
  ReleaseMetricsResponse,
  ReleaseSignalResponse,
} from "../api/types";
import { IssuesPanel } from "../components/IssuesPanel";
import { MetricsPanel } from "../components/MetricsPanel";
import { RecommendationsPanel } from "../components/RecommendationsPanel";
import { ReportExportActions } from "../components/ReportExportActions";
import { ReleaseSelector } from "../components/ReleaseSelector";
import { SignalSummaryPanel } from "../components/SignalSummaryPanel";

type ReleaseCommandPageProps = {
  releases: Release[];
  selectedProjectKey: string | null;
  selectedReleaseId: string | null;
  selectedRelease: Release | null;
  metrics: ReleaseMetricsResponse | null;
  charts: ReleaseChartsResponse | null;
  signal: ReleaseSignalResponse | null;
  refreshNonce: number;
  isLoadingReleases: boolean;
  isLoadingDetails: boolean;
  isRecomputingRelease: boolean;
  focusedMetricName: keyof MetricValues | null;
  onSelectRelease: (releaseId: string | null) => void;
  onRecomputeRelease: () => void;
  onSelectIssue: (issueKey: string) => void;
};

export function ReleaseCommandPage({
  releases,
  selectedProjectKey,
  selectedReleaseId,
  selectedRelease,
  metrics,
  charts,
  signal,
  refreshNonce,
  isLoadingReleases,
  isLoadingDetails,
  isRecomputingRelease,
  focusedMetricName,
  onSelectRelease,
  onRecomputeRelease,
  onSelectIssue,
}: ReleaseCommandPageProps) {
  return (
    <>
      {selectedReleaseId ? (
        <>
          <section className="panel report-export-panel">
            <div className="panel-heading">
              <div>
                <h2>Executive Reporting</h2>
              </div>
              <ReportExportActions
                entity="release"
                entityId={selectedReleaseId}
                filenameLabel={selectedRelease?.name ?? selectedReleaseId}
              />
              <ReportExportActions
                entity="overview"
                entityId={selectedReleaseId}
                filenameLabel={selectedRelease?.name ?? selectedReleaseId}
              />
            </div>
          </section>
          <SignalSummaryPanel
            signal={signal}
            isLoading={isLoadingDetails}
            releases={releases}
            selectedProjectKey={selectedProjectKey}
            refreshNonce={refreshNonce}
          />
          <MetricsPanel
            metrics={metrics}
            charts={charts}
            isLoading={isLoadingDetails}
            onSelectIssue={onSelectIssue}
            focusedMetricName={focusedMetricName}
          />
          {metrics ? (
            <RecommendationsPanel
              recommendations={metrics.recommendations}
              title="Report Recommendations"
              className="panel release-command-recommendations-panel"
            />
          ) : null}
        </>
      ) : null}

      <ReleaseSelector
        releases={releases}
        selectedReleaseId={selectedReleaseId}
        selectedRelease={selectedRelease}
        isLoading={isLoadingReleases}
        isRecomputing={isRecomputingRelease}
        onChange={onSelectRelease}
        onRecompute={onRecomputeRelease}
      />
      {selectedReleaseId ? (
        <IssuesPanel releaseId={selectedReleaseId} refreshNonce={refreshNonce} onSelectIssue={onSelectIssue} />
      ) : null}
    </>
  );
}
