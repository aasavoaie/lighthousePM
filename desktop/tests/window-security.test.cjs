const assert = require("node:assert/strict");
const test = require("node:test");

const {
  configureWindowNavigationGuards,
  createMainWindowOptions,
  delegateApprovedExternalUrl,
} = require("../src/window-security.cjs");

test("main window options enforce the approved Electron security settings", () => {
  const options = createMainWindowOptions({
    preloadPath: "C:/LighthousePM/preload.cjs",
    partition: "lighthousepm-ephemeral",
  });

  assert.deepEqual(options.webPreferences, {
    preload: "C:/LighthousePM/preload.cjs",
    partition: "lighthousepm-ephemeral",
    contextIsolation: true,
    nodeIntegration: false,
    sandbox: true,
    webSecurity: true,
    allowRunningInsecureContent: false,
    spellcheck: false,
  });
  assert.equal(options.show, false);
});

test("external delegation opens canonical HTTPS URLs only", () => {
  const opened = [];
  const openExternal = (url) => opened.push(url);

  assert.deepEqual(
    delegateApprovedExternalUrl("https://example.com/docs?q=1", openExternal),
    { ok: true },
  );
  assert.deepEqual(opened, ["https://example.com/docs?q=1"]);

  for (const url of [
    "http://example.com/",
    "file:///C:/Windows/System32/calc.exe",
    "javascript:alert(1)",
    "not a URL",
  ]) {
    assert.deepEqual(delegateApprovedExternalUrl(url, openExternal), {
      ok: false,
      message: "Only HTTPS links can be opened externally.",
    });
  }
  assert.deepEqual(opened, ["https://example.com/docs?q=1"]);
});

test("window guards block foreign navigation, new windows, and webviews", () => {
  const listeners = new Map();
  let windowOpenHandler = null;
  const opened = [];
  const webContents = {
    on: (eventName, handler) => listeners.set(eventName, handler),
    setWindowOpenHandler: (handler) => {
      windowOpenHandler = handler;
    },
  };
  configureWindowNavigationGuards({
    webContents,
    getRendererOrigin: () => "http://127.0.0.1:5173",
    openExternal: (url) => opened.push(url),
  });

  let prevented = false;
  listeners.get("will-navigate")(
    { preventDefault: () => { prevented = true; } },
    "http://127.0.0.1:5173/releases",
  );
  assert.equal(prevented, false);

  listeners.get("will-navigate")(
    { preventDefault: () => { prevented = true; } },
    "https://example.com/docs",
  );
  assert.equal(prevented, true);
  assert.deepEqual(opened, ["https://example.com/docs"]);

  prevented = false;
  listeners.get("will-navigate")(
    { preventDefault: () => { prevented = true; } },
    "http://example.com/unsafe",
  );
  assert.equal(prevented, true);
  assert.deepEqual(opened, ["https://example.com/docs"]);

  assert.deepEqual(windowOpenHandler({ url: "https://example.com/window" }), { action: "deny" });
  assert.deepEqual(windowOpenHandler({ url: "file:///C:/unsafe" }), { action: "deny" });
  assert.deepEqual(opened, ["https://example.com/docs", "https://example.com/window"]);

  let webviewPrevented = false;
  listeners.get("will-attach-webview")({
    preventDefault: () => {
      webviewPrevented = true;
    },
  });
  assert.equal(webviewPrevented, true);
});
