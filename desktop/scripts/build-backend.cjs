const { spawnSync } = require("node:child_process");
const fs = require("node:fs");
const path = require("node:path");

const repositoryRoot = path.resolve(__dirname, "../..");
const backendDirectory = path.join(repositoryRoot, "backend");
const executableName = process.platform === "win32" ? "lighthousepm-backend.exe" : "lighthousepm-backend";
const outputExecutable = path.join(backendDirectory, "dist", "lighthousepm-backend", executableName);

function findPython() {
  const candidates = [
    process.env.LIGHTHOUSE_PYTHON,
    path.join(repositoryRoot, ".venv", "Scripts", "python.exe"),
    path.join(repositoryRoot, ".venv", "bin", "python"),
    process.platform === "win32" ? "python.exe" : "python3",
  ].filter(Boolean);

  for (const candidate of candidates) {
    if (path.isAbsolute(candidate) && !fs.existsSync(candidate)) {
      continue;
    }
    return candidate;
  }
  throw new Error("Python was not found. Set LIGHTHOUSE_PYTHON to the project virtual-environment interpreter.");
}

const result = spawnSync(
  findPython(),
  ["-m", "PyInstaller", "--noconfirm", "--clean", "lighthousepm_backend.spec"],
  {
    cwd: backendDirectory,
    env: process.env,
    stdio: "inherit",
  },
);

if (result.error) {
  throw result.error;
}
if (result.status !== 0) {
  process.exit(result.status ?? 1);
}
if (!fs.existsSync(outputExecutable)) {
  throw new Error(`Packaged backend was not created at ${outputExecutable}`);
}

console.log(`Packaged backend: ${outputExecutable}`);
