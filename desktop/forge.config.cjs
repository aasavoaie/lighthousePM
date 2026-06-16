const path = require("node:path");

function envValue(name) {
  const value = process.env[name];
  return value && value.trim() ? value.trim() : undefined;
}

const iconPath = path.resolve(__dirname, "assets", "icon");
const squirrelConfig = {
  name: "lighthousepm",
  title: "LighthousePM",
  authors: "LighthousePM",
  owners: "LighthousePM",
  exe: "LighthousePM.exe",
  setupExe: "LighthousePM-Setup.exe",
  setupIcon: `${iconPath}.ico`,
  noMsi: true,
};

const iconUrl = envValue("LIGHTHOUSEPM_ICON_URL");
if (iconUrl) {
  squirrelConfig.iconUrl = iconUrl;
}

const updateUrl = envValue("LIGHTHOUSEPM_UPDATE_URL");
if (updateUrl) {
  squirrelConfig.remoteReleases = updateUrl;
}

const updateToken = envValue("LIGHTHOUSEPM_UPDATE_TOKEN");
if (updateToken) {
  squirrelConfig.remoteToken = updateToken;
}

const signWithParams = envValue("WINDOWS_SIGN_WITH_PARAMS");
const certificateFile = envValue("WINDOWS_CERTIFICATE_FILE");
const certificatePassword = envValue("WINDOWS_CERTIFICATE_PASSWORD");
if (signWithParams) {
  squirrelConfig.signWithParams = signWithParams;
} else if (certificateFile && certificatePassword) {
  squirrelConfig.certificateFile = certificateFile;
  squirrelConfig.certificatePassword = certificatePassword;
}

module.exports = {
  packagerConfig: {
    asar: true,
    appCopyright: "Copyright (c) LighthousePM",
    executableName: "LighthousePM",
    extraResource: ["../frontend/dist", "../backend/dist/lighthousepm-backend"],
    icon: iconPath,
    win32metadata: {
      CompanyName: "LighthousePM",
      FileDescription: "LighthousePM Desktop",
      InternalName: "LighthousePM",
      OriginalFilename: "LighthousePM.exe",
      ProductName: "LighthousePM",
    },
  },
  rebuildConfig: {},
  makers: [
    {
      name: "@electron-forge/maker-squirrel",
      config: squirrelConfig,
    },
    {
      name: "@electron-forge/maker-zip",
      platforms: ["win32"],
    },
  ],
};
