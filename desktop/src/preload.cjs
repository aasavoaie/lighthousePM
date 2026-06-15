const { contextBridge } = require("electron");

contextBridge.exposeInMainWorld(
  "lighthouseDesktop",
  Object.freeze({
    isElectron: true,
    platform: process.platform,
  }),
);
