"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
const auth_1 = require("./auth");
function assertEqual(actual, expected, message) {
    if (actual !== expected) {
        throw new Error(`${message}: expected ${String(expected)}, received ${String(actual)}`);
    }
}
(0, auth_1.clearBrowserApiToken)();
assertEqual((0, auth_1.getBrowserApiToken)(), null, "the browser token starts empty");
(0, auth_1.setBrowserApiToken)(" token with spaces ");
assertEqual((0, auth_1.getBrowserApiToken)(), " token with spaces ", "the configured token remains opaque");
(0, auth_1.setBrowserApiToken)("browser-token");
const options = (0, auth_1.withBrowserApiToken)({
    method: "POST",
    headers: { "Content-Type": "application/json" },
});
const headers = new Headers(options.headers);
assertEqual(options.method, "POST", "request options are preserved");
assertEqual(headers.get("Content-Type"), "application/json", "existing headers are preserved");
assertEqual(headers.get("Authorization"), "Bearer browser-token", "the bearer header uses the memory token");
(0, auth_1.setBrowserApiToken)("   ");
assertEqual((0, auth_1.getBrowserApiToken)(), null, "a whitespace-only token is treated as absent");
assertEqual(new Headers((0, auth_1.withBrowserApiToken)().headers).has("Authorization"), false, "absent tokens add no header");
let authenticationFailures = 0;
const unsubscribe = (0, auth_1.subscribeToApiAuthenticationFailures)(() => {
    authenticationFailures += 1;
});
(0, auth_1.reportApiAuthenticationFailure)();
unsubscribe();
(0, auth_1.reportApiAuthenticationFailure)();
assertEqual(authenticationFailures, 1, "authentication failure subscriptions can be removed");
const authenticationError = new auth_1.ApiAuthenticationError();
assertEqual(authenticationError.name, "ApiAuthenticationError", "authentication failures have a stable type");
(0, auth_1.clearBrowserApiToken)();
