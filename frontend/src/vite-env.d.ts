/// <reference types="vite/client" />

interface Window {
  lighthouseDesktop?: {
    isElectron: boolean;
    platform: string;
  };
}
