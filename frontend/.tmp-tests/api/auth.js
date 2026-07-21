"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.ApiAuthenticationError = void 0;
exports.setBrowserApiToken = setBrowserApiToken;
exports.clearBrowserApiToken = clearBrowserApiToken;
exports.getBrowserApiToken = getBrowserApiToken;
exports.withBrowserApiToken = withBrowserApiToken;
exports.subscribeToApiAuthenticationFailures = subscribeToApiAuthenticationFailures;
exports.reportApiAuthenticationFailure = reportApiAuthenticationFailure;
let browserApiToken = null;
const authenticationFailureListeners = new Set();
class ApiAuthenticationError extends Error {
    constructor() {
        super("The API token is missing or invalid.");
        this.name = "ApiAuthenticationError";
    }
}
exports.ApiAuthenticationError = ApiAuthenticationError;
function setBrowserApiToken(token) {
    browserApiToken = token.trim() ? token : null;
}
function clearBrowserApiToken() {
    browserApiToken = null;
}
function getBrowserApiToken() {
    return browserApiToken;
}
function withBrowserApiToken(options) {
    if (!browserApiToken) {
        return options ?? {};
    }
    const headers = new Headers(options?.headers);
    headers.set("Authorization", `Bearer ${browserApiToken}`);
    return { ...options, headers };
}
function subscribeToApiAuthenticationFailures(listener) {
    authenticationFailureListeners.add(listener);
    return () => {
        authenticationFailureListeners.delete(listener);
    };
}
function reportApiAuthenticationFailure() {
    for (const listener of authenticationFailureListeners) {
        listener();
    }
}
