const assert = require("node:assert/strict");
const test = require("node:test");

const {
  isAllowedAppNavigation,
  isAllowedExternalUrl,
  isLocalApiPath,
  shouldAttachLocalApiToken,
} = require("../src/security-policy.cjs");

const rendererOrigin = "http://127.0.0.1:5173";

test("application navigation requires the exact active renderer origin", () => {
  assert.equal(isAllowedAppNavigation(`${rendererOrigin}/releases`, rendererOrigin), true);
  assert.equal(isAllowedAppNavigation(`${rendererOrigin}/reports?depth=full`, rendererOrigin), true);

  for (const targetUrl of [
    "http://localhost:5173/",
    "http://127.0.0.1:5174/",
    "https://127.0.0.1:5173/",
    "https://example.com/",
    "not a URL",
    "",
  ]) {
    assert.equal(isAllowedAppNavigation(targetUrl, rendererOrigin), false, targetUrl);
  }
  assert.equal(isAllowedAppNavigation(`${rendererOrigin}/`, null), false);
});

test("external delegation accepts valid HTTPS URLs only", () => {
  assert.equal(isAllowedExternalUrl("https://example.com/path?q=1"), true);

  for (const targetUrl of [
    "http://example.com/",
    "file:///C:/Windows/System32/calc.exe",
    "data:text/html,unsafe",
    "javascript:alert(1)",
    "not a URL",
    "",
  ]) {
    assert.equal(isAllowedExternalUrl(targetUrl), false, targetUrl);
  }
});

test("the local API path boundary excludes similar prefixes", () => {
  assert.equal(isLocalApiPath("/api"), true);
  assert.equal(isLocalApiPath("/api/"), true);
  assert.equal(isLocalApiPath("/api/releases"), true);

  for (const pathname of ["/", "/API", "/api-evil", "/apis", "/apiary"]) {
    assert.equal(isLocalApiPath(pathname), false, pathname);
  }
});

test("the local API token is limited to the exact development renderer API boundary", () => {
  assert.equal(shouldAttachLocalApiToken(`${rendererOrigin}/api`, rendererOrigin), true);
  assert.equal(shouldAttachLocalApiToken(`${rendererOrigin}/api/releases?limit=1`, rendererOrigin), true);

  for (const targetUrl of [
    `${rendererOrigin}/api-evil`,
    `${rendererOrigin}/`,
    "http://localhost:5173/api/releases",
    "http://127.0.0.1:8000/api/releases",
    "https://example.com/api/releases",
    "not a URL",
  ]) {
    assert.equal(shouldAttachLocalApiToken(targetUrl, rendererOrigin), false, targetUrl);
  }
});
