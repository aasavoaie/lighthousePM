import { type FormEvent, type ReactNode, useEffect, useState } from "react";

import { apiClient } from "../api/client";
import {
  ApiAuthenticationError,
  clearBrowserApiToken,
  setBrowserApiToken,
  subscribeToApiAuthenticationFailures,
} from "../api/auth";

type AuthenticationState = "checking" | "required" | "authenticated";

export function ApiAuthenticationGate({ children }: { children: ReactNode }) {
  const isElectron = Boolean(window.lighthouseDesktop?.isElectron);
  const [authenticationState, setAuthenticationState] = useState<AuthenticationState>(
    isElectron ? "authenticated" : "checking"
  );
  const [candidateToken, setCandidateToken] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [isChecking, setIsChecking] = useState(false);

  useEffect(() => {
    if (isElectron) {
      return;
    }
    return subscribeToApiAuthenticationFailures(() => {
      clearBrowserApiToken();
      setCandidateToken("");
      setError("The API token is missing or invalid.");
      setAuthenticationState("required");
    });
  }, [isElectron]);

  useEffect(() => {
    if (isElectron) {
      return;
    }
    let isActive = true;

    async function checkAnonymousAccess() {
      try {
        await apiClient.getJiraConfiguration();
        if (isActive) {
          setAuthenticationState("authenticated");
        }
      } catch (requestError) {
        if (!isActive) {
          return;
        }
        if (requestError instanceof ApiAuthenticationError) {
          setAuthenticationState("required");
          return;
        }
        // Let the workspace display ordinary backend-connectivity errors.
        setAuthenticationState("authenticated");
      }
    }

    void checkAnonymousAccess();
    return () => {
      isActive = false;
    };
  }, [isElectron]);

  async function submitToken(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!candidateToken.trim() || isChecking) {
      setError("Enter the API token supplied by the LighthousePM operator.");
      return;
    }

    setIsChecking(true);
    setError(null);
    setBrowserApiToken(candidateToken);
    try {
      await apiClient.getJiraConfiguration();
      setCandidateToken("");
      setAuthenticationState("authenticated");
    } catch (requestError) {
      clearBrowserApiToken();
      setCandidateToken("");
      setError(
        requestError instanceof ApiAuthenticationError
          ? "The API token is missing or invalid."
          : requestError instanceof Error
            ? requestError.message
            : "Could not verify the API token."
      );
      setAuthenticationState("required");
    } finally {
      setIsChecking(false);
    }
  }

  if (authenticationState === "authenticated") {
    return children;
  }

  if (authenticationState === "checking") {
    return (
      <main className="api-auth-shell">
        <section className="api-auth-card" aria-live="polite">
          <p className="detail-hero-kicker">LighthousePM Security</p>
          <h1>Checking API access</h1>
          <p>Confirming whether this local deployment requires an API token.</p>
        </section>
      </main>
    );
  }

  return (
    <main className="api-auth-shell">
      <form className="api-auth-card" onSubmit={(event) => void submitToken(event)}>
        <p className="detail-hero-kicker">LighthousePM Security</p>
        <h1>API token required</h1>
        <p>Enter the bearer token supplied by the operator of this LighthousePM deployment.</p>
        <label>
          <span>API token</span>
          <input
            type="password"
            name="lighthouse-api-token"
            value={candidateToken}
            autoComplete="off"
            spellCheck={false}
            disabled={isChecking}
            onChange={(event) => setCandidateToken(event.target.value)}
          />
        </label>
        <button type="submit" className="primary-button" disabled={isChecking}>
          {isChecking ? "Checking..." : "Continue"}
        </button>
        <p className="muted">The token is kept in memory only and is cleared when this page closes.</p>
        {error ? <p className="error-text" role="alert">{error}</p> : null}
      </form>
    </main>
  );
}
