const { shouldAttachLocalApiToken } = require("./security-policy.cjs");

const EPHEMERAL_STORAGE_TYPES = [
  "cookies",
  "localstorage",
  "indexdb",
  "cachestorage",
  "websql",
  "serviceworkers",
  "shadercache",
];

async function configureDesktopSessionSecurity({
  appSession,
  devRendererOrigin,
  isDevelopmentRendererConfigured,
  getLocalApiToken,
}) {
  await appSession.clearCache();
  await appSession.clearStorageData({ storages: EPHEMERAL_STORAGE_TYPES });
  appSession.setPermissionCheckHandler(() => false);
  appSession.setPermissionRequestHandler((_webContents, _permission, callback) => callback(false));

  appSession.webRequest.onBeforeSendHeaders((details, callback) => {
    const localApiToken = getLocalApiToken();
    if (
      localApiToken &&
      isDevelopmentRendererConfigured &&
      shouldAttachLocalApiToken(details.url, devRendererOrigin)
    ) {
      callback({
        requestHeaders: {
          ...details.requestHeaders,
          Authorization: `Bearer ${localApiToken}`,
        },
      });
      return;
    }
    callback({ requestHeaders: details.requestHeaders });
  });

  if (typeof appSession.setDevicePermissionHandler === "function") {
    appSession.setDevicePermissionHandler(() => false);
  }
}

module.exports = {
  EPHEMERAL_STORAGE_TYPES,
  configureDesktopSessionSecurity,
};
