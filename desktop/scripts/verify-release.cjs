const { spawnSync } = require("node:child_process");
const fs = require("node:fs");
const path = require("node:path");

const root = path.resolve(__dirname, "..");
const packageJson = require(path.join(root, "package.json"));
const version = packageJson.version;

const requiredFiles = [
  "assets/icon.ico",
  "assets/icon.png",
  "assets/icon.svg",
  "out/LighthousePM-win32-x64/LighthousePM.exe",
  "out/LighthousePM-win32-x64/resources/app.asar",
  "out/LighthousePM-win32-x64/resources/dist/index.html",
  "out/LighthousePM-win32-x64/resources/lighthousepm-backend/lighthousepm-backend.exe",
  "out/make/squirrel.windows/x64/LighthousePM-Setup.exe",
  "out/make/squirrel.windows/x64/RELEASES",
  `out/make/squirrel.windows/x64/lighthousepm-${version}-full.nupkg`,
  `out/make/zip/win32/x64/LighthousePM-win32-x64-${version}.zip`,
];

function fail(message) {
  console.error(`Release verification failed: ${message}`);
  process.exitCode = 1;
}

function assertFile(relativePath) {
  const filePath = path.join(root, relativePath);
  if (!fs.existsSync(filePath) || !fs.statSync(filePath).isFile()) {
    fail(`missing ${relativePath}`);
    return;
  }
  if (fs.statSync(filePath).size === 0) {
    fail(`${relativePath} is empty`);
  }
}

function powershellLiteral(value) {
  return `'${value.replace(/'/g, "''")}'`;
}

function verifyWindowsSignature(relativePath) {
  const filePath = path.join(root, relativePath);
  const command = `(Get-AuthenticodeSignature -LiteralPath ${powershellLiteral(filePath)}).Status`;
  const result = spawnSync("powershell.exe", ["-NoProfile", "-Command", command], {
    encoding: "utf8",
    windowsHide: true,
  });
  if (result.status !== 0) {
    fail(`could not inspect Authenticode signature for ${relativePath}`);
    return;
  }

  const status = result.stdout.trim();
  if (status !== "Valid") {
    fail(`${relativePath} signature status is ${status || "unknown"}`);
  }
}

for (const relativePath of requiredFiles) {
  assertFile(relativePath);
}

const releasesPath = path.join(root, "out/make/squirrel.windows/x64/RELEASES");
if (fs.existsSync(releasesPath)) {
  const releases = fs.readFileSync(releasesPath, "utf8");
  if (!releases.includes(`lighthousepm-${version}-full.nupkg`)) {
    fail("RELEASES does not reference the current full NuGet package");
  }
}

if (process.env.REQUIRE_WINDOWS_CODE_SIGNING === "1") {
  verifyWindowsSignature("out/make/squirrel.windows/x64/LighthousePM-Setup.exe");
  verifyWindowsSignature("out/LighthousePM-win32-x64/LighthousePM.exe");
} else {
  console.log("Skipping Authenticode verification. Set REQUIRE_WINDOWS_CODE_SIGNING=1 to require signed artifacts.");
}

if (process.exitCode) {
  process.exit();
}

console.log("Release artifacts verified.");
