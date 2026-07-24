const assert = require("node:assert/strict");
const test = require("node:test");

const {
  EPHEMERAL_STORAGE_TYPES,
  configureDesktopSessionSecurity,
} = require("../src/session-security.cjs");

function sessionHarness() {
  const calls = {
    clearCache: 0,
    clearedStorages: null,
    permissionCheck: null,
    permissionRequest: null,
    devicePermission: null,
    beforeSendHeaders: null,
  };
  const appSession = {
    clearCache: async () => {
      calls.clearCache += 1;
    },
    clearStorageData: async ({ storages }) => {
      calls.clearedStorages = storages;
    },
    setPermissionCheckHandler: (handler) => {
      calls.permissionCheck = handler;
    },
    setPermissionRequestHandler: (handler) => {
      calls.permissionRequest = handler;
    },
    setDevicePermissionHandler: (handler) => {
      calls.devicePermission = handler;
    },
    webRequest: {
      onBeforeSendHeaders: (handler) => {
        calls.beforeSendHeaders = handler;
      },
    },
  };
  return { appSession, calls };
}

function applyHeaders(handler, url, requestHeaders = {}) {
  let result;
  handler({ url, requestHeaders }, (value) => {
    result = value;
  });
  return result;
}

test("desktop session clears ephemeral state and denies every permission path", async () => {
  const { appSession, calls } = sessionHarness();
  await configureDesktopSessionSecurity({
    appSession,
    devRendererOrigin: "http://127.0.0.1:5173",
    isDevelopmentRendererConfigured: false,
    getLocalApiToken: () => null,
  });

  assert.equal(calls.clearCache, 1);
  assert.deepEqual(calls.clearedStorages, EPHEMERAL_STORAGE_TYPES);
  assert.equal(calls.permissionCheck({}, "camera", "https://example.com"), false);
  assert.equal(calls.devicePermission({ deviceType: "usb" }), false);

  let permissionDecision = null;
  calls.permissionRequest({}, "notifications", (decision) => {
    permissionDecision = decision;
  });
  assert.equal(permissionDecision, false);
});

test("session attaches the token only to the exact configured development API origin", async () => {
  const { appSession, calls } = sessionHarness();
  let localApiToken = "desktop-secret";
  await configureDesktopSessionSecurity({
    appSession,
    devRendererOrigin: "http://127.0.0.1:5173",
    isDevelopmentRendererConfigured: true,
    getLocalApiToken: () => localApiToken,
  });

  assert.deepEqual(
    applyHeaders(calls.beforeSendHeaders, "http://127.0.0.1:5173/api/releases", { Accept: "application/json" }),
    {
      requestHeaders: {
        Accept: "application/json",
        Authorization: "Bearer desktop-secret",
      },
    },
  );

  for (const url of [
    "http://127.0.0.1:5173/api-evil",
    "http://localhost:5173/api/releases",
    "https://example.com/api/releases",
  ]) {
    assert.deepEqual(
      applyHeaders(calls.beforeSendHeaders, url, { Accept: "application/json" }),
      { requestHeaders: { Accept: "application/json" } },
    );
  }

  localApiToken = null;
  assert.deepEqual(
    applyHeaders(calls.beforeSendHeaders, "http://127.0.0.1:5173/api/releases"),
    { requestHeaders: {} },
  );
});

test("session never attaches a token when the development renderer is not configured", async () => {
  const { appSession, calls } = sessionHarness();
  await configureDesktopSessionSecurity({
    appSession,
    devRendererOrigin: "http://127.0.0.1:5173",
    isDevelopmentRendererConfigured: false,
    getLocalApiToken: () => "desktop-secret",
  });

  assert.deepEqual(
    applyHeaders(calls.beforeSendHeaders, "http://127.0.0.1:5173/api/releases"),
    { requestHeaders: {} },
  );
});
