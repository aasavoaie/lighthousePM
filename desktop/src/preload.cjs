const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld(
  "lighthouseDesktop",
  Object.freeze({
    isElectron: true,
    platform: process.platform,
    storeJiraToken: (token) => ipcRenderer.invoke("jira-token:store", token),
    getStorageInfo: () => ipcRenderer.invoke("desktop-storage:info"),
    backupData: () => ipcRenderer.invoke("desktop-storage:backup"),
    restoreData: () => ipcRenderer.invoke("desktop-storage:restore"),
    clearData: () => ipcRenderer.invoke("desktop-storage:clear-data"),
    factoryReset: () => ipcRenderer.invoke("desktop-storage:factory-reset"),
    revealDataFolder: () => ipcRenderer.invoke("desktop-storage:reveal"),
  }),
);
