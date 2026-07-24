const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");

const {
  IPC_REJECTION_MESSAGE,
  isTrustedIpcSender,
  registerTrustedIpcHandler,
  validatedJiraToken,
  validatedPdfPayload,
  withoutIpcArguments,
} = require("../src/ipc-security.cjs");

const rendererOrigin = "http://127.0.0.1:5173";

function trustedBoundary() {
  const mainFrame = { url: `${rendererOrigin}/settings` };
  const webContents = {
    isDestroyed: () => false,
    mainFrame,
  };
  const mainWindow = {
    isDestroyed: () => false,
    webContents,
  };
  return {
    event: { sender: webContents, senderFrame: mainFrame },
    mainFrame,
    mainWindow,
    webContents,
  };
}

test("IPC sender trust requires the active window main frame and exact renderer origin", () => {
  const boundary = trustedBoundary();
  assert.equal(
    isTrustedIpcSender(boundary.event, {
      mainWindow: boundary.mainWindow,
      rendererOrigin,
    }),
    true,
  );

  const rejected = [
    { event: boundary.event, mainWindow: null, origin: rendererOrigin },
    {
      event: boundary.event,
      mainWindow: { ...boundary.mainWindow, isDestroyed: () => true },
      origin: rendererOrigin,
    },
    {
      event: boundary.event,
      mainWindow: {
        ...boundary.mainWindow,
        webContents: { ...boundary.webContents, isDestroyed: () => true },
      },
      origin: rendererOrigin,
    },
    {
      event: { ...boundary.event, sender: {} },
      mainWindow: boundary.mainWindow,
      origin: rendererOrigin,
    },
    {
      event: { ...boundary.event, senderFrame: null },
      mainWindow: boundary.mainWindow,
      origin: rendererOrigin,
    },
    {
      event: { ...boundary.event, senderFrame: { url: `${rendererOrigin}/nested` } },
      mainWindow: boundary.mainWindow,
      origin: rendererOrigin,
    },
    {
      event: boundary.event,
      mainWindow: boundary.mainWindow,
      origin: null,
    },
  ];

  for (const value of rejected) {
    assert.equal(
      isTrustedIpcSender(value.event, {
        mainWindow: value.mainWindow,
        rendererOrigin: value.origin,
      }),
      false,
    );
  }

  boundary.mainFrame.url = "https://example.com/settings";
  assert.equal(
    isTrustedIpcSender(boundary.event, {
      mainWindow: boundary.mainWindow,
      rendererOrigin,
    }),
    false,
  );
});

test("trusted registration rejects invalid senders before executing a handler", async () => {
  const registered = new Map();
  const ipcMain = {
    handle: (channel, handler) => registered.set(channel, handler),
  };
  const boundary = trustedBoundary();
  let callCount = 0;
  registerTrustedIpcHandler({
    ipcMain,
    channel: "test:channel",
    getMainWindow: () => boundary.mainWindow,
    getRendererOrigin: () => rendererOrigin,
    handler: (value) => {
      callCount += 1;
      return `accepted:${value}`;
    },
  });

  const handler = registered.get("test:channel");
  assert.equal(await handler(boundary.event, "payload"), "accepted:payload");
  assert.equal(callCount, 1);

  await assert.rejects(
    async () => handler({ sender: {}, senderFrame: null }, "payload"),
    new RegExp(IPC_REJECTION_MESSAGE),
  );
  assert.equal(callCount, 1);
});

test("argument-free storage handlers reject renderer-supplied values before side effects", () => {
  let callCount = 0;
  const handler = withoutIpcArguments("desktop-storage:backup", () => {
    callCount += 1;
    return { ok: true };
  });

  assert.deepEqual(handler(), { ok: true });
  assert.equal(callCount, 1);
  assert.throws(
    () => handler("C:/renderer-supplied-path"),
    /desktop-storage:backup does not accept renderer arguments/,
  );
  assert.equal(callCount, 1);
});

test("Jira token validation rejects non-string and empty payloads", () => {
  assert.equal(validatedJiraToken("  secret-token  "), "secret-token");
  assert.throws(() => validatedJiraToken(null), /must be a string/);
  assert.throws(() => validatedJiraToken({ token: "secret-token" }), /must be a string/);
  assert.throws(() => validatedJiraToken("   "), /is required/);
});

test("PDF validation requires a filename string and non-empty binary data", () => {
  const data = new Uint8Array([0x25, 0x50, 0x44, 0x46]);
  assert.deepEqual(validatedPdfPayload({ filename: "report.pdf", data }), {
    filename: "report.pdf",
    data,
  });

  assert.throws(() => validatedPdfPayload(null), /payload is invalid/);
  assert.throws(() => validatedPdfPayload([]), /payload is invalid/);
  assert.throws(() => validatedPdfPayload({ filename: 42, data }), /filename must be a string/);
  assert.throws(
    () => validatedPdfPayload({ filename: "report.pdf", data: [1, 2, 3] }),
    /data must be binary/,
  );
  assert.throws(
    () => validatedPdfPayload({ filename: "report.pdf", data: new Uint8Array() }),
    /PDF export was empty/,
  );
});

test("preload exposes exactly the IPC channels registered by the main process", () => {
  const desktopRoot = path.resolve(__dirname, "..");
  const preloadSource = fs.readFileSync(path.join(desktopRoot, "src", "preload.cjs"), "utf8");
  const mainSource = fs.readFileSync(path.join(desktopRoot, "src", "main.cjs"), "utf8");
  const invokedChannels = [
    ...preloadSource.matchAll(/ipcRenderer\.invoke\("([^"]+)"/g),
  ].map((match) => match[1]).sort();
  const registeredChannels = [
    ...mainSource.matchAll(/registerDesktopIpcHandler\(\s*"([^"]+)"/g),
  ].map((match) => match[1]).sort();

  assert.deepEqual(invokedChannels, registeredChannels);
  assert.equal(new Set(invokedChannels).size, invokedChannels.length);
  assert.doesNotMatch(preloadSource, /ipcRenderer\.(?:send|sendSync|on|once|postMessage)\s*\(/);
  assert.doesNotMatch(preloadSource, /\b(?:send|invoke)\s*:/);
  assert.match(preloadSource, /Object\.freeze\(\{/);
});
