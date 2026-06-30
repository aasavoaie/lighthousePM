import type { ReactNode } from "react";

export type MetricStatus = "good" | "warning" | "critical" | "neutral";
export type MetricImpact = "positive" | "negative" | "neutral" | "unknown";

interface MetricStatusCardProps {
  id?: string;
  title: string;
  value: string;
  status: MetricStatus;
  isHighlighted?: boolean;
  comparison?: string | null;
  comparisonImpact?: MetricImpact;
  details?: string[];
  infoText?: string;
  badge?: string | null;
  badgeTitle?: string | null;
  children?: ReactNode;
}

interface MetricCategorySectionProps {
  title: string;
  summary?: string;
  children: ReactNode;
}

const statusLabels: Record<MetricStatus, string> = {
  good: "Good",
  warning: "Warning",
  critical: "Critical",
  neutral: "Info",
};

export function MetricStatusCard({
  id,
  title,
  value,
  status,
  isHighlighted = false,
  comparison,
  comparisonImpact = "unknown",
  details = [],
  infoText,
  badge,
  badgeTitle,
  children,
}: MetricStatusCardProps) {
  return (
    <article
      id={id}
      className={`metric-card metric-status-card metric-status-${status} ${isHighlighted ? "metric-card-highlighted" : ""}`}
    >
      <div className="metric-status-heading">
        <span className="metric-status-dot" aria-hidden="true" />
        <h3>{title}</h3>
        <div className="metric-status-actions">
          {infoText ? (
            <button type="button" className="info-button compact-info-button" title={infoText} aria-label={`${title} info`}>
              i
            </button>
          ) : null}
          {badge ? (
            <span className="metric-muted-badge" title={badgeTitle ?? undefined}>
              {badge}
            </span>
          ) : null}
          <span className="metric-status-label">{statusLabels[status]}</span>
        </div>
      </div>
      <strong>{value}</strong>
      {comparison ? <p className={`metric-comparison metric-impact-${comparisonImpact}`}>{comparison}</p> : null}
      {details.length > 0 ? (
        <ul className="metric-detail-list">
          {details.map((detail) => (
            <li key={detail}>{detail}</li>
          ))}
        </ul>
      ) : null}
      {children}
    </article>
  );
}

export function MetricCategorySection({ title, summary, children }: MetricCategorySectionProps) {
  return (
    <div className="metric-category-section">
      <h3>{title}</h3>
      {summary ? <p className="metric-category-summary">{summary}</p> : null}
      <div className="metric-grid">{children}</div>
    </div>
  );
}

export function formatSignedDelta(delta: number, formatter: (value: number) => string) {
  if (delta === 0) {
    return "No change since previous snapshot";
  }
  const sign = delta > 0 ? "+" : "-";
  return `${sign}${formatter(Math.abs(delta))} since previous snapshot`;
}

export function getDeltaImpact(
  delta: number | null,
  direction: "higher-is-better" | "lower-is-better" | "neutral"
): MetricImpact {
  if (delta === null || delta === 0 || direction === "neutral") {
    return "neutral";
  }
  if (direction === "higher-is-better") {
    return delta > 0 ? "positive" : "negative";
  }
  return delta < 0 ? "positive" : "negative";
}
