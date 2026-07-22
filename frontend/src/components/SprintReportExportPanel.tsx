import { ReportExportActions } from "./ReportExportActions";

type SprintReportExportPanelProps = {
  sprintId: string | null;
  sprintName: string | null;
};

export function SprintReportExportPanel({ sprintId, sprintName }: SprintReportExportPanelProps) {
  return (
    <section className="panel report-export-panel">
      <div className="panel-heading">
        <div>
          <h2>Executive Reporting</h2>
        </div>
        <ReportExportActions
          entity="sprint"
          entityId={sprintId}
          filenameLabel={sprintName ?? sprintId ?? "sprint"}
        />
      </div>
    </section>
  );
}
