import type {
  MetricValues,
  Release,
  ReleaseChartsResponse,
  ReleaseMetricsResponse,
  ReleaseSignalResponse,
} from "../api/types";
import { OverviewDashboard } from "../components/OverviewDashboard";
import { ReportExportActions } from "../components/ReportExportActions";

type OverviewPageProps = {
  projectKey: string | null;
  releaseId: string;
  release: Release | null;
  metrics: ReleaseMetricsResponse | null;
  charts: ReleaseChartsResponse | null;
  signal: ReleaseSignalResponse | null;
  refreshNonce: number;
  isLoading: boolean;
  onOpenReports: () => void;
  onOpenReleaseMetric: (metricName: keyof MetricValues) => void;
};

export function OverviewPage({
  projectKey,
  releaseId,
  release,
  metrics,
  charts,
  signal,
  refreshNonce,
  isLoading,
  onOpenReports,
  onOpenReleaseMetric,
}: OverviewPageProps) {
  return (
    <>
      <section className="panel report-export-panel overview-export-panel">
        <div className="panel-heading">
          <div>
            <h2>Executive Reporting</h2>
          </div>
          <ReportExportActions
            entity="overview"
            entityId={releaseId}
            filenameLabel={release?.name ?? releaseId}
          />
        </div>
      </section>
      <OverviewDashboard
        projectKey={projectKey}
        release={release}
        metrics={metrics}
        charts={charts}
        signal={signal}
        refreshNonce={refreshNonce}
        isLoading={isLoading}
        onOpenReports={onOpenReports}
        onOpenReleaseMetric={onOpenReleaseMetric}
      />
    </>
  );
}
