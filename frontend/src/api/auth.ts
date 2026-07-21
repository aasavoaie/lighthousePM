let browserApiToken: string | null = null;
const authenticationFailureListeners = new Set<() => void>();

export class ApiAuthenticationError extends Error {
  constructor() {
    super("The API token is missing or invalid.");
    this.name = "ApiAuthenticationError";
  }
}

export function setBrowserApiToken(token: string) {
  browserApiToken = token.trim() ? token : null;
}

export function clearBrowserApiToken() {
  browserApiToken = null;
}

export function getBrowserApiToken() {
  return browserApiToken;
}

export function withBrowserApiToken(options?: RequestInit): RequestInit {
  if (!browserApiToken) {
    return options ?? {};
  }
  const headers = new Headers(options?.headers);
  headers.set("Authorization", `Bearer ${browserApiToken}`);
  return { ...options, headers };
}

export function subscribeToApiAuthenticationFailures(listener: () => void) {
  authenticationFailureListeners.add(listener);
  return () => {
    authenticationFailureListeners.delete(listener);
  };
}

export function reportApiAuthenticationFailure() {
  for (const listener of authenticationFailureListeners) {
    listener();
  }
}
