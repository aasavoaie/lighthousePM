import {
  ApiAuthenticationError,
  clearBrowserApiToken,
  getBrowserApiToken,
  reportApiAuthenticationFailure,
  setBrowserApiToken,
  subscribeToApiAuthenticationFailures,
  withBrowserApiToken,
} from "./auth";

function assertEqual<T>(actual: T, expected: T, message: string) {
  if (actual !== expected) {
    throw new Error(`${message}: expected ${String(expected)}, received ${String(actual)}`);
  }
}

clearBrowserApiToken();
assertEqual(getBrowserApiToken(), null, "the browser token starts empty");

setBrowserApiToken(" token with spaces ");
assertEqual(getBrowserApiToken(), " token with spaces ", "the configured token remains opaque");

setBrowserApiToken("browser-token");
const options = withBrowserApiToken({
  method: "POST",
  headers: { "Content-Type": "application/json" },
});
const headers = new Headers(options.headers);
assertEqual(options.method, "POST", "request options are preserved");
assertEqual(headers.get("Content-Type"), "application/json", "existing headers are preserved");
assertEqual(headers.get("Authorization"), "Bearer browser-token", "the bearer header uses the memory token");

setBrowserApiToken("   ");
assertEqual(getBrowserApiToken(), null, "a whitespace-only token is treated as absent");
assertEqual(new Headers(withBrowserApiToken().headers).has("Authorization"), false, "absent tokens add no header");

let authenticationFailures = 0;
const unsubscribe = subscribeToApiAuthenticationFailures(() => {
  authenticationFailures += 1;
});
reportApiAuthenticationFailure();
unsubscribe();
reportApiAuthenticationFailure();
assertEqual(authenticationFailures, 1, "authentication failure subscriptions can be removed");

const authenticationError = new ApiAuthenticationError();
assertEqual(authenticationError.name, "ApiAuthenticationError", "authentication failures have a stable type");

clearBrowserApiToken();
