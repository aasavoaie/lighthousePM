const { isAllowedAppNavigation } = require("./security-policy.cjs");

const IPC_REJECTION_MESSAGE = "Desktop IPC request rejected.";

function isTrustedIpcSender(event, { mainWindow, rendererOrigin }) {
  if (!mainWindow || typeof mainWindow.isDestroyed !== "function" || mainWindow.isDestroyed()) {
    return false;
  }

  const activeWebContents = mainWindow.webContents;
  if (
    !activeWebContents ||
    (typeof activeWebContents.isDestroyed === "function" && activeWebContents.isDestroyed()) ||
    event?.sender !== activeWebContents
  ) {
    return false;
  }

  const senderFrame = event.senderFrame;
  if (!senderFrame || senderFrame !== activeWebContents.mainFrame) {
    return false;
  }

  return isAllowedAppNavigation(senderFrame.url, rendererOrigin);
}

function registerTrustedIpcHandler({
  ipcMain,
  channel,
  getMainWindow,
  getRendererOrigin,
  handler,
}) {
  ipcMain.handle(channel, (event, ...args) => {
    if (
      !isTrustedIpcSender(event, {
        mainWindow: getMainWindow(),
        rendererOrigin: getRendererOrigin(),
      })
    ) {
      throw new Error(IPC_REJECTION_MESSAGE);
    }
    return handler(...args);
  });
}

function withoutIpcArguments(channel, handler) {
  return (...args) => {
    if (args.length !== 0) {
      throw new Error(`${channel} does not accept renderer arguments.`);
    }
    return handler();
  };
}

function validatedJiraToken(token) {
  if (typeof token !== "string") {
    throw new Error("Jira API token must be a string.");
  }
  const normalizedToken = token.trim();
  if (!normalizedToken) {
    throw new Error("Jira API token is required.");
  }
  return normalizedToken;
}

function validatedPdfPayload(payload) {
  if (!payload || typeof payload !== "object" || Array.isArray(payload)) {
    throw new Error("PDF export payload is invalid.");
  }
  if (typeof payload.filename !== "string") {
    throw new Error("PDF export filename must be a string.");
  }
  if (!(payload.data instanceof Uint8Array)) {
    throw new Error("PDF export data must be binary.");
  }
  if (payload.data.byteLength === 0) {
    throw new Error("PDF export was empty.");
  }
  return {
    filename: payload.filename,
    data: payload.data,
  };
}

module.exports = {
  IPC_REJECTION_MESSAGE,
  isTrustedIpcSender,
  registerTrustedIpcHandler,
  validatedJiraToken,
  validatedPdfPayload,
  withoutIpcArguments,
};
