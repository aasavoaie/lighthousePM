/// <reference types="vite/client" />

interface Window {
  lighthouseDesktop?: {
    isElectron: boolean;
    platform: string;
    storeJiraToken?: (token: string) => Promise<{ ok: boolean }>;
  };
}
