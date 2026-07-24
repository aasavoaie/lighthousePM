const {
  isAllowedAppNavigation,
  isAllowedExternalUrl,
} = require("./security-policy.cjs");

function createMainWindowOptions({ preloadPath, partition }) {
  return {
    width: 1440,
    height: 960,
    minWidth: 1100,
    minHeight: 700,
    show: false,
    autoHideMenuBar: true,
    backgroundColor: "#f4f7fb",
    title: "LighthousePM",
    webPreferences: {
      preload: preloadPath,
      partition,
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
      webSecurity: true,
      allowRunningInsecureContent: false,
      spellcheck: false,
    },
  };
}

function delegateApprovedExternalUrl(targetUrl, openExternal) {
  if (!isAllowedExternalUrl(targetUrl)) {
    return { ok: false, message: "Only HTTPS links can be opened externally." };
  }
  void openExternal(new URL(targetUrl).toString());
  return { ok: true };
}

function configureWindowNavigationGuards({
  webContents,
  getRendererOrigin,
  openExternal,
}) {
  webContents.on("will-navigate", (event, targetUrl) => {
    if (isAllowedAppNavigation(targetUrl, getRendererOrigin())) {
      return;
    }
    event.preventDefault();
    delegateApprovedExternalUrl(targetUrl, openExternal);
  });

  webContents.setWindowOpenHandler(({ url }) => {
    delegateApprovedExternalUrl(url, openExternal);
    return { action: "deny" };
  });

  webContents.on("will-attach-webview", (event) => {
    event.preventDefault();
  });
}

module.exports = {
  configureWindowNavigationGuards,
  createMainWindowOptions,
  delegateApprovedExternalUrl,
};
