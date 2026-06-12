import type { DriverAnalysis } from "../api/types";

interface BiggestDriverCardProps {
  driver: DriverAnalysis;
  heading?: string;
}

function formatImpact(value: number) {
  if (value === 0) {
    return "0 points";
  }
  const formatted = Number.isInteger(value) ? value.toFixed(0) : value.toFixed(1);
  return `${value > 0 ? "+" : ""}${formatted} points`;
}

function formatContribution(value: number) {
  const formatted = Number.isInteger(value) ? value.toFixed(0) : value.toFixed(1);
  return `${formatted}%`;
}

export function BiggestDriverCard({ driver, heading = "Biggest Driver" }: BiggestDriverCardProps) {
  const impactClass = driver.impact < 0 ? "negative" : driver.impact > 0 ? "positive" : "neutral";

  return (
    <section className={`biggest-driver-card driver-impact-${impactClass}`} aria-label={heading}>
      <div className="biggest-driver-heading">
        <div>
          <span>{heading}</span>
          <h3>{driver.title}</h3>
        </div>
        <span className="biggest-driver-category">{driver.category}</span>
      </div>
      <dl className="biggest-driver-stats">
        <div>
          <dt>Impact</dt>
          <dd>{formatImpact(driver.impact)}</dd>
        </div>
        <div>
          <dt>Contribution</dt>
          <dd>{formatContribution(driver.contributionPercent)}</dd>
        </div>
      </dl>
      <p>{driver.explanation}</p>
      <div className="biggest-driver-action">
        <strong>Recommended action</strong>
        <p>{driver.recommendation}</p>
      </div>
    </section>
  );
}
