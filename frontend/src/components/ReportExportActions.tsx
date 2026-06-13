import { useState } from "react";

import { apiClient } from "../api/client";
import type { ReportDepth } from "../api/types";

type ReportEntity = "release" | "sprint" | "overview";

interface ReportExportActionsProps {
  entity: ReportEntity;
  entityId: string | null;
  filenameLabel: string;
}

function saveBlob(blob: Blob, filename: string) {
  const url = window.URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  document.body.append(anchor);
  anchor.click();
  anchor.remove();
  window.URL.revokeObjectURL(url);
}

function reportFilename(entity: ReportEntity, entityId: string, depth: ReportDepth, filenameLabel: string) {
  const normalizedLabel = filenameLabel.trim().replace(/[^a-z0-9]+/gi, "-").replace(/^-|-$/g, "").toLowerCase();
  return `lighthousepm-${entity}-${normalizedLabel || entityId}-${depth}.pdf`;
}

function overviewFilename(entityId: string, filenameLabel: string) {
  const normalizedLabel = filenameLabel.trim().replace(/[^a-z0-9]+/gi, "-").replace(/^-|-$/g, "").toLowerCase();
  return `lighthousepm-overview-${normalizedLabel || entityId}.pdf`;
}

export function ReportExportActions({ entity, entityId, filenameLabel }: ReportExportActionsProps) {
  const [exportingDepth, setExportingDepth] = useState<ReportDepth | "overview" | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function handleOverviewExport() {
    if (!entityId || exportingDepth) {
      return;
    }
    setExportingDepth("overview");
    setError(null);
    try {
      const blob = await apiClient.downloadOverviewReport(entityId);
      saveBlob(blob, overviewFilename(entityId, filenameLabel));
    } catch (exportError) {
      setError(exportError instanceof Error ? exportError.message : "Failed to export PDF report.");
    } finally {
      setExportingDepth(null);
    }
  }

  async function handleExport(depth: ReportDepth) {
    if (!entityId || exportingDepth) {
      return;
    }
    setExportingDepth(depth);
    setError(null);
    try {
      const blob =
        entity === "release"
          ? await apiClient.downloadReleaseReport(entityId, depth)
          : await apiClient.downloadSprintReport(entityId, depth);
      saveBlob(blob, reportFilename(entity, entityId, depth, filenameLabel));
    } catch (exportError) {
      setError(exportError instanceof Error ? exportError.message : "Failed to export PDF report.");
    } finally {
      setExportingDepth(null);
    }
  }

  if (entity === "overview") {
    return (
      <div className="report-export-actions" aria-label="PDF report exports">
        <div className="report-export-buttons">
          <button
            type="button"
            className="primary-button compact-button"
            disabled={!entityId || exportingDepth !== null}
            onClick={() => void handleOverviewExport()}
          >
            {exportingDepth === "overview" ? "Exporting..." : "Export Overview PDF"}
          </button>
        </div>
        {error ? <p className="error-text report-export-error">{error}</p> : null}
      </div>
    );
  }

  return (
    <div className="report-export-actions" aria-label="PDF report exports">
      <div className="report-export-buttons">
        <button
          type="button"
          className="secondary-button compact-button"
          disabled={!entityId || exportingDepth !== null}
          onClick={() => void handleExport("summary")}
        >
          {exportingDepth === "summary" ? "Exporting..." : "Export Summary PDF"}
        </button>
        <button
          type="button"
          className="primary-button compact-button"
          disabled={!entityId || exportingDepth !== null}
          onClick={() => void handleExport("full")}
        >
          {exportingDepth === "full" ? "Exporting..." : "Export Full Report PDF"}
        </button>
      </div>
      {error ? <p className="error-text report-export-error">{error}</p> : null}
    </div>
  );
}
