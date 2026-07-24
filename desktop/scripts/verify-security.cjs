const { spawnSync } = require("node:child_process");
const fs = require("node:fs");
const path = require("node:path");

const desktopRoot = path.resolve(__dirname, "..");
const repositoryRoot = path.resolve(desktopRoot, "..");

function fail(message) {
  console.error(`Security acceptance failed: ${message}`);
  process.exit(1);
}

function commandWorks(command, args) {
  const result = spawnSync(command, args, {
    cwd: repositoryRoot,
    encoding: "utf8",
    windowsHide: true,
  });
  return result.status === 0;
}

function findPython() {
  const configuredPython = process.env.LIGHTHOUSE_PYTHON;
  if (configuredPython) {
    if (!commandWorks(configuredPython, ["--version"])) {
      fail("LIGHTHOUSE_PYTHON does not identify a working Python interpreter.");
    }
    return configuredPython;
  }

  const repositoryCandidates = [
    path.join(repositoryRoot, ".venv", "Scripts", "python.exe"),
    path.join(repositoryRoot, ".venv", "bin", "python"),
  ];
  for (const candidate of repositoryCandidates) {
    if (fs.existsSync(candidate) && commandWorks(candidate, ["--version"])) {
      return candidate;
    }
  }

  for (const candidate of ["python3", "python"]) {
    if (commandWorks(candidate, ["--version"])) {
      return candidate;
    }
  }
  fail("No working Python interpreter was found.");
}

function run(label, command, args, cwd, environment = process.env) {
  console.log(`\n[security acceptance] ${label}`);
  const result = spawnSync(command, args, {
    cwd,
    env: environment,
    stdio: "inherit",
    windowsHide: true,
  });
  if (result.error) {
    fail(`${label} could not start: ${result.error.message}`);
  }
  if (result.status !== 0) {
    fail(`${label} exited with status ${result.status ?? "unknown"}.`);
  }
}

const python = findPython();
const npmCli = process.env.npm_execpath;
if (!npmCli || !fs.existsSync(npmCli)) {
  fail("npm CLI path is unavailable; run this gate through npm run verify:security.");
}
const dockerAvailable = commandWorks(
  "docker",
  ["info", "--format", "{{.ServerVersion}}"],
);
const dockerRequired = process.env.LIGHTHOUSE_REQUIRE_DOCKER_SECURITY === "1";

if (dockerRequired && !dockerAvailable) {
  fail("Docker security acceptance is required, but the Docker daemon is unavailable.");
}

const backendEnvironment = { ...process.env };
if (dockerAvailable) {
  backendEnvironment.LIGHTHOUSE_REQUIRE_DOCKER_SECURITY = "1";
  console.log("Docker is available; the isolated container security smoke test is required.");
} else {
  delete backendEnvironment.LIGHTHOUSE_REQUIRE_DOCKER_SECURITY;
  console.log("Docker is unavailable; container smoke is skipped. Set LIGHTHOUSE_REQUIRE_DOCKER_SECURITY=1 to require it.");
}

run(
  "backend tests",
  python,
  ["-m", "pytest", "tests", "-q"],
  path.join(repositoryRoot, "backend"),
  backendEnvironment,
);
run(
  "backend lint",
  python,
  ["-m", "ruff", "check", "app", "tests", "alembic"],
  path.join(repositoryRoot, "backend"),
);
run(
  "frontend tests",
  process.execPath,
  [npmCli, "test"],
  path.join(repositoryRoot, "frontend"),
);
run(
  "frontend production build",
  process.execPath,
  [npmCli, "run", "build"],
  path.join(repositoryRoot, "frontend"),
);
run("desktop tests", process.execPath, [npmCli, "test"], desktopRoot);

console.log("\nSecurity acceptance verified.");
