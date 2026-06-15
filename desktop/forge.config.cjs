module.exports = {
  packagerConfig: {
    asar: true,
    executableName: "LighthousePM",
    extraResource: ["../frontend/dist", "../backend/dist/lighthousepm-backend"],
  },
  rebuildConfig: {},
  makers: [
    {
      name: "@electron-forge/maker-squirrel",
      config: {
        name: "lighthousepm",
        setupExe: "LighthousePM-Setup.exe",
        noMsi: true,
      },
    },
    {
      name: "@electron-forge/maker-zip",
      platforms: ["win32"],
    },
  ],
};
