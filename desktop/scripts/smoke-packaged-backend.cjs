const { spawn, spawnSync } = require("node:child_process");
const crypto = require("node:crypto");
const fs = require("node:fs");
const http = require("node:http");
const net = require("node:net");
const os = require("node:os");
const path = require("node:path");

const LOOPBACK_HOST = "127.0.0.1";
const STARTUP_TIMEOUT_MS = 60_000;
const SHUTDOWN_TIMEOUT_MS = 10_000;
const REQUEST_TIMEOUT_MS = 3_000;
const MAX_RESPONSE_BYTES = 1_000_000;
const MAX_DIAGNOSTIC_CHARACTERS = 16_000;

function backendExecutablePath(repositoryRoot = path.resolve(__dirname, "../..")) {
  return path.join(
    repositoryRoot,
    "backend",
    "dist",
    "lighthousepm-backend",
    "lighthousepm-backend.exe"
  );
}

function requireBackendExecutable(executablePath) {
  if (!fs.existsSync(executablePath) || !fs.statSync(executablePath).isFile()) {
    throw new Error(
      `Packaged backend not found at ${executablePath}. Run npm run build:backend first.`
    );
  }
}

function sanitizedBackendEnvironment(token, environment = process.env) {
  const sanitized = {};
  const excludedNames = new Set([
    "APP_ENV",
    "APP_HOST",
    "APP_PORT",
    "CORS_ORIGINS",
    "DATABASE_URL",
    "DEPLOYMENT_MODE",
    "ELECTRON_RUN_AS_NODE",
    "LIGHTHOUSE_API_TOKEN",
    "LIGHTHOUSE_API_TOKEN_FILE",
    "LIGHTHOUSE_CONFIG_FILE",
  ]);

  for (const [name, value] of Object.entries(environment)) {
    const normalizedName = name.toUpperCase();
    if (
      excludedNames.has(normalizedName) ||
      normalizedName.startsWith("JIRA_") ||
      normalizedName.startsWith("POSTGRES_")
    ) {
      continue;
    }
    sanitized[name] = value;
  }

  sanitized.LIGHTHOUSE_API_TOKEN = token;
  return sanitized;
}

function redact(value, secret) {
  const text = String(value ?? "");
  return secret ? text.split(secret).join("[REDACTED]") : text;
}

function appendDiagnostic(current, chunk) {
  return `${current}${chunk}`.slice(-MAX_DIAGNOSTIC_CHARACTERS);
}

function captureProcessDiagnostics(childProcess) {
  const diagnostics = { stdout: "", stderr: "", processError: null };

  childProcess.on("error", (error) => {
    diagnostics.processError = error;
  });

  for (const streamName of ["stdout", "stderr"]) {
    const stream = childProcess[streamName];
    stream?.setEncoding("utf8");
    stream?.on("data", (chunk) => {
      diagnostics[streamName] = appendDiagnostic(diagnostics[streamName], chunk);
    });
  }

  return diagnostics;
}

function diagnosticText(diagnostics, token) {
  const sections = [];
  if (diagnostics.processError) {
    sections.push(`process error:\n${redact(diagnostics.processError.message, token)}`);
  }
  for (const streamName of ["stdout", "stderr"]) {
    const content = redact(diagnostics[streamName], token).trim();
    if (content) {
      sections.push(`${streamName}:\n${content}`);
    }
  }
  return sections.length > 0 ? sections.join("\n") : "No backend diagnostics were captured.";
}

function reserveLoopbackPort() {
  return new Promise((resolve, reject) => {
    const server = net.createServer();
    server.unref();
    server.once("error", reject);
    server.listen(0, LOOPBACK_HOST, () => {
      const address = server.address();
      if (!address || typeof address === "string") {
        server.close();
        reject(new Error("Could not reserve a loopback port."));
        return;
      }
      server.close((error) => {
        if (error) {
          reject(error);
        } else {
          resolve(address.port);
        }
      });
    });
  });
}

function requestJson(port, pathname, token) {
  return new Promise((resolve, reject) => {
    const headers = token ? { Authorization: `Bearer ${token}` } : {};
    const request = http.request(
      {
        host: LOOPBACK_HOST,
        port,
        path: pathname,
        method: "GET",
        headers,
      },
      (response) => {
        let body = "";
        response.setEncoding("utf8");
        response.on("data", (chunk) => {
          body += chunk;
          if (Buffer.byteLength(body, "utf8") > MAX_RESPONSE_BYTES) {
            response.destroy(new Error("Backend response exceeded the smoke-test size limit."));
          }
        });
        response.on("end", () => {
          try {
            resolve({
              statusCode: response.statusCode,
              body: body ? JSON.parse(body) : null,
            });
          } catch {
            reject(new Error(`Backend returned invalid JSON for ${pathname}.`));
          }
        });
      }
    );

    request.setTimeout(REQUEST_TIMEOUT_MS, () => {
      request.destroy(new Error(`Backend request timed out for ${pathname}.`));
    });
    request.once("error", reject);
    request.end();
  });
}

function validateHealthResponse(response) {
  if (response.statusCode !== 200 || response.body?.status !== "ok") {
    throw new Error("Packaged backend health response was not ready.");
  }
}

function validateAnonymousResponse(response) {
  if (
    response.statusCode !== 401 ||
    response.body?.detail !== "API authentication failed."
  ) {
    throw new Error("Packaged backend did not enforce authentication for releases.");
  }
}

function validateEmptyReleasesResponse(response) {
  const body = response.body;
  const keys = body && typeof body === "object" ? Object.keys(body).sort() : [];
  const expectedKeys = ["items", "limit", "skip", "total"];
  if (
    response.statusCode !== 200 ||
    JSON.stringify(keys) !== JSON.stringify(expectedKeys) ||
    !Array.isArray(body.items) ||
    body.items.length !== 0 ||
    body.skip !== 0 ||
    body.limit !== 1 ||
    body.total !== 0
  ) {
    throw new Error("Packaged backend did not return the expected empty releases response.");
  }
}

function delay(milliseconds) {
  return new Promise((resolve) => setTimeout(resolve, milliseconds));
}

function waitForSpawn(childProcess) {
  if (childProcess.pid) {
    return Promise.resolve();
  }
  return new Promise((resolve, reject) => {
    const onSpawn = () => {
      cleanup();
      resolve();
    };
    const onError = (error) => {
      cleanup();
      reject(error);
    };
    function cleanup() {
      childProcess.off("spawn", onSpawn);
      childProcess.off("error", onError);
    }
    childProcess.once("spawn", onSpawn);
    childProcess.once("error", onError);
  });
}

async function waitForHealth(
  childProcess,
  port,
  timeoutMs = STARTUP_TIMEOUT_MS,
  request = requestJson,
  pause = delay,
  diagnostics
) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    if (diagnostics?.processError) {
      throw new Error(`Packaged backend process failed: ${diagnostics.processError.message}`);
    }
    if (childProcess.exitCode !== null) {
      throw new Error(`Packaged backend exited early with code ${childProcess.exitCode}.`);
    }
    try {
      const response = await request(port, "/health");
      validateHealthResponse(response);
      return;
    } catch {
      await pause(250);
    }
  }
  throw new Error(`Packaged backend did not become healthy within ${timeoutMs} ms.`);
}

function waitForExit(childProcess, timeoutMs) {
  if (childProcess.exitCode !== null) {
    return Promise.resolve();
  }
  return new Promise((resolve, reject) => {
    const timeout = setTimeout(() => {
      cleanup();
      reject(new Error(`Packaged backend did not exit within ${timeoutMs} ms.`));
    }, timeoutMs);
    const onExit = () => {
      cleanup();
      resolve();
    };
    const onError = (error) => {
      cleanup();
      reject(error);
    };
    function cleanup() {
      clearTimeout(timeout);
      childProcess.off("exit", onExit);
      childProcess.off("error", onError);
    }
    childProcess.once("exit", onExit);
    childProcess.once("error", onError);
  });
}

async function terminateBackend(childProcess, timeoutMs = SHUTDOWN_TIMEOUT_MS) {
  if (!childProcess || childProcess.exitCode !== null || !childProcess.pid) {
    return;
  }

  childProcess.kill();
  try {
    await waitForExit(childProcess, timeoutMs);
    return;
  } catch (initialError) {
    if (process.platform !== "win32" || !childProcess.pid) {
      throw initialError;
    }

    const forced = spawnSync("taskkill.exe", ["/pid", String(childProcess.pid), "/T", "/F"], {
      encoding: "utf8",
      windowsHide: true,
    });
    if (forced.status !== 0) {
      throw new Error("Packaged backend could not be terminated after its smoke test.");
    }
    await waitForExit(childProcess, timeoutMs);
  }
}

function removeTemporaryDirectory(directory) {
  if (!directory) {
    return;
  }
  fs.rmSync(directory, { recursive: true, force: true, maxRetries: 3, retryDelay: 100 });
  if (fs.existsSync(directory)) {
    throw new Error(`Packaged-backend smoke data was not removed: ${directory}`);
  }
}

async function runPackagedBackendSmoke() {
  const repositoryRoot = path.resolve(__dirname, "../..");
  const executablePath = backendExecutablePath(repositoryRoot);
  requireBackendExecutable(executablePath);

  const temporaryDirectory = fs.mkdtempSync(
    path.join(os.tmpdir(), "lighthousepm-packaged-backend-")
  );
  const databasePath = path.join(temporaryDirectory, "lighthouse.db");
  const token = crypto.randomBytes(32).toString("hex");
  let childProcess;
  let diagnostics = { stdout: "", stderr: "", processError: null };
  let smokeError;
  let cleanupError;

  try {
    const port = await reserveLoopbackPort();
    childProcess = spawn(
      executablePath,
      [
        "--host",
        LOOPBACK_HOST,
        "--port",
        String(port),
        "--database-path",
        databasePath,
        "--app-env",
        "prod",
        "--log-level",
        "info",
      ],
      {
        cwd: path.dirname(executablePath),
        env: sanitizedBackendEnvironment(token),
        stdio: ["ignore", "pipe", "pipe"],
        windowsHide: true,
      }
    );
    diagnostics = captureProcessDiagnostics(childProcess);
    await waitForSpawn(childProcess);
    await waitForHealth(childProcess, port, STARTUP_TIMEOUT_MS, requestJson, delay, diagnostics);
    validateAnonymousResponse(await requestJson(port, "/releases?skip=0&limit=1"));
    validateEmptyReleasesResponse(
      await requestJson(port, "/releases?skip=0&limit=1", token)
    );
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    smokeError = new Error(
      `${message}\n${diagnosticText(diagnostics, token)}`,
      { cause: error }
    );
  } finally {
    const cleanupErrors = [];
    try {
      await terminateBackend(childProcess);
    } catch (error) {
      cleanupErrors.push(error);
    }
    try {
      removeTemporaryDirectory(temporaryDirectory);
    } catch (error) {
      cleanupErrors.push(error);
    }
    if (cleanupErrors.length === 1) {
      cleanupError = cleanupErrors[0];
    } else if (cleanupErrors.length > 1) {
      cleanupError = new AggregateError(cleanupErrors, "Packaged-backend cleanup failed.");
    }
  }

  if (smokeError && cleanupError) {
    throw new AggregateError(
      [smokeError, cleanupError],
      `${smokeError.message}\nCleanup failed: ${cleanupError.message}`
    );
  }
  if (smokeError) {
    throw smokeError;
  }
  if (cleanupError) {
    throw cleanupError;
  }

  console.log("Packaged backend smoke test passed and temporary data was removed.");
}

if (require.main === module) {
  runPackagedBackendSmoke().catch((error) => {
    console.error(`Packaged backend smoke test failed: ${error.message}`);
    process.exitCode = 1;
  });
}

module.exports = {
  LOOPBACK_HOST,
  appendDiagnostic,
  backendExecutablePath,
  diagnosticText,
  removeTemporaryDirectory,
  reserveLoopbackPort,
  requireBackendExecutable,
  runPackagedBackendSmoke,
  sanitizedBackendEnvironment,
  terminateBackend,
  validateAnonymousResponse,
  validateEmptyReleasesResponse,
  validateHealthResponse,
  waitForHealth,
  waitForSpawn,
};
