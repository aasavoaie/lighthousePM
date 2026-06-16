/// <reference types="vite/client" />

interface LighthouseDesktopOperationResult {
  ok: boolean;
  message?: string;
  path?: string;
}

interface LighthouseDesktopStorageInfo {
  isElectron: boolean;
  backendOrigin: string | null;
  paths: {
    userDataDirectory: string;
    dataDirectory: string;
    logsDirectory: string;
    secretsDirectory: string;
    databasePath: string;
    configPath: string;
    tokenPath: string;
  };
  usage: {
    databaseBytes: number;
    configBytes: number;
    tokenBytes: number;
    logsBytes: number;
    totalBytes: number;
  };
  exists: {
    database: boolean;
    config: boolean;
    encryptedToken: boolean;
  };
}

interface Window {
  lighthouseDesktop?: {
    isElectron: boolean;
    platform: string;
    storeJiraToken?: (token: string) => Promise<{ ok: boolean }>;
    savePdf?: (payload: { filename: string; data: Uint8Array }) => Promise<LighthouseDesktopOperationResult>;
    openExternal?: (url: string) => Promise<LighthouseDesktopOperationResult>;
    getStorageInfo?: () => Promise<LighthouseDesktopStorageInfo>;
    backupData?: () => Promise<LighthouseDesktopOperationResult>;
    restoreData?: () => Promise<LighthouseDesktopOperationResult>;
    clearData?: () => Promise<LighthouseDesktopOperationResult>;
    factoryReset?: () => Promise<LighthouseDesktopOperationResult>;
    revealDataFolder?: () => Promise<LighthouseDesktopOperationResult>;
  };
}
