import type { ReleaseSignalResponse } from "../api/types";

interface SignalSummaryPanelProps {
  signal: ReleaseSignalResponse | null;
  isLoading: boolean;
}

function signalClassName(signalValue: string | null) {
  if (signalValue === "RED") {
    return "signal-badge signal-red";
  }
  if (signalValue === "YELLOW") {
    return "signal-badge signal-yellow";
  }
  if (signalValue === "GREEN") {
    return "signal-badge signal-green";
  }
  return "signal-badge signal-unknown";
}

export function SignalSummaryPanel({ signal, isLoading }: SignalSummaryPanelProps) {
  return (
    <section className="panel signal-panel">
      <div className="panel-heading">
        <h2>Signal</h2>
        <span className={signalClassName(signal?.signal ?? null)}>{signal?.signal ?? "N/A"}</span>
      </div>
      {isLoading ? <p className="muted">Loading signal...</p> : null}
      {!isLoading && signal && signal.reasons.length > 0 ? (
        <ul className="reason-list">
          {signal.reasons.map((reason) => (
            <li key={reason}>{reason}</li>
          ))}
        </ul>
      ) : null}
      {!isLoading && signal && signal.reasons.length === 0 ? (
        <p className="muted">Signal has not been computed yet.</p>
      ) : null}
      {!isLoading && signal?.updated_at ? (
        <p className="timestamp">Updated {new Date(signal.updated_at).toLocaleString()}</p>
      ) : null}
    </section>
  );
}