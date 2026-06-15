const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld(
  "lighthouseDesktop",
  Object.freeze({
    isElectron: true,
    platform: process.platform,
    storeJiraToken: (token) => ipcRenderer.invoke("jira-token:store", token),
  }),
);
