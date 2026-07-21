const { app, autoUpdater, BrowserWindow, dialog, ipcMain, safeStorage, session, shell } = require("electron");
const { spawn, spawnSync } = require("node:child_process");
const crypto = require("node:crypto");
const fs = require("node:fs");
const http = require("node:http");
const net = require("node:net");
const path = require("node:path");

const {
  CONFIG_PATH: BACKUP_CONFIG_PATH,
  DATABASE_PATH: BACKUP_DATABASE_PATH,
  TOKEN_PATH: BACKUP_TOKEN_PATH,
  publishValidatedSettingsBackup,
  validateSettingsBackup,
} = require("./backup.cjs");
const { createDesktopOperationLock, stopProcessAndWait } = require("./operation-control.cjs");
const {
  TARGET_LOCATION_APPLICATION_SIDECAR,
  TARGET_LOCATION_USER_DATA,
} = require("./storage-recovery.cjs");
const {
  StorageTransactionError,
  applyFileReplacementPlan,
  recoverInterruptedStorageOperation,
  replaceFileAtomically,
  runStorageTransaction,
} = require("./storage-transaction.cjs");

const LOOPBACK_HOST = "127.0.0.1";
const DEV_RENDERER_ORIGIN = "http://127.0.0.1:5173";
const DEV_BACKEND_PORT = 8000;
const DEV_RENDERER_URL = process.env.ELECTRON_RENDERER_URL;
const BACKEND_STARTUP_TIMEOUT_MS = 30000;
const BACKEND_SHUTDOWN_TIMEOUT_MS = 10000;
const BACKEND_HEALTH_RETRY_MS = 200;
const APP_SESSION_PARTITION = "lighthousepm-ephemeral";
const BACKEND_LOG_MAX_BYTES = 1024 * 1024;
const BACKEND_LOG_MAX_FILES = 5;
const BACKEND_LOG_RETENTION_DAYS = 14;
const WINDOWS_APP_USER_MODEL_ID = "com.squirrel.lighthousepm.LighthousePM";
const UPDATE_FEED_URL = process.env.LIGHTHOUSEPM_UPDATE_URL;
const RECOVERY_DATABASE_WAL_PATH = `${BACKUP_DATABASE_PATH}-wal`;
const RECOVERY_DATABASE_SHM_PATH = `${BACKUP_DATABASE_PATH}-shm`;

const CONTENT_TYPES = new Map([
  [".css", "text/css; charset=utf-8"],
  [".html", "text/html; charset=utf-8"],
  [".ico", "image/x-icon"],
  [".jpg", "image/jpeg"],
  [".jpeg", "image/jpeg"],
  [".js", "text/javascript; charset=utf-8"],
  [".json", "application/json; charset=utf-8"],
  [".png", "image/png"],
  [".svg", "image/svg+xml"],
  [".webp", "image/webp"],
  [".woff", "font/woff"],
  [".woff2", "font/woff2"],
]);

let mainWindow = null;
let backendOrigin = null;
let backendProcess = null;
let localApiToken = null;
let rendererServer = null;
let rendererOrigin = null;
let isQuitting = false;
const intentionallyStoppedBackendProcesses = new WeakSet();
const desktopStorageOperations = createDesktopOperationLock();

app.enableSandbox();
if (process.platform === "win32") {
  app.setAppUserModelId(WINDOWS_APP_USER_MODEL_ID);
}
app.commandLine.appendSwitch("disable-http-cache");

function spawnSquirrelUpdate(args) {
  const updateExecutable = path.resolve(path.dirname(process.execPath), "..", "Update.exe");
  try {
    return spawn(updateExecutable, args, { detached: true, windowsHide: true });
  } catch {
    return null;
  }
}

function handleSquirrelStartupEvent() {
  if (process.platform !== "win32") {
    return false;
  }

  const squirrelEvent = process.argv[1];
  const executableName = path.basename(process.execPath);
  switch (squirrelEvent) {
    case "--squirrel-install":
    case "--squirrel-updated":
      spawnSquirrelUpdate(["--createShortcut", executableName]);
      setTimeout(() => app.quit(), 1000);
      return true;
    case "--squirrel-uninstall":
      spawnSquirrelUpdate(["--removeShortcut", executableName]);
      setTimeout(() => app.quit(), 1000);
      return true;
    case "--squirrel-obsolete":
      app.quit();
      return true;
    default:
      return false;
  }
}

if (handleSquirrelStartupEvent()) {
  return;
}

const hasSingleInstanceLock = app.requestSingleInstanceLock();
if (!hasSingleInstanceLock) {
  app.quit();
}

function getRendererDirectory() {
  if (app.isPackaged) {
    return path.join(process.resourcesPath, "dist");
  }
  return path.resolve(__dirname, "../../frontend/dist");
}

function getBackendExecutable() {
  const executableName = process.platform === "win32" ? "lighthousepm-backend.exe" : "lighthousepm-backend";
  if (app.isPackaged) {
    return path.join(process.resourcesPath, "lighthousepm-backend", executableName);
  }
  return path.resolve(__dirname, "../../backend/dist/lighthousepm-backend", executableName);
}

function getBackendConfigPaths() {
  const userConfigPath = path.join(app.getPath("userData"), "backend.env");
  const sidecarConfigPath = app.isPackaged
    ? path.join(path.dirname(app.getPath("exe")), "backend.env")
    : path.resolve(__dirname, "../../backend/.env");
  const configLocation = !app.isPackaged || fs.existsSync(sidecarConfigPath)
    ? TARGET_LOCATION_APPLICATION_SIDECAR
    : TARGET_LOCATION_USER_DATA;
  return {
    userConfigPath,
    sidecarConfigPath,
    configLocation,
    configPath:
      configLocation === TARGET_LOCATION_APPLICATION_SIDECAR
        ? sidecarConfigPath
        : userConfigPath,
  };
}

function getBackendEnvFile() {
  return getBackendConfigPaths().configPath;
}

function getDesktopDataPaths() {
  const userDataDirectory = app.getPath("userData");
  const dataDirectory = path.join(userDataDirectory, "data");
  const logsDirectory = path.join(userDataDirectory, "logs");
  const secretsDirectory = path.join(userDataDirectory, "secrets");
  const databasePath = path.join(dataDirectory, "lighthouse.db");
  const configPaths = getBackendConfigPaths();
  return {
    userDataDirectory,
    dataDirectory,
    logsDirectory,
    secretsDirectory,
    databasePath,
    ...configPaths,
    tokenPath: getEncryptedJiraTokenPath(),
  };
}

function getEncryptedJiraTokenPath() {
  return path.join(app.getPath("userData"), "secrets", "jira-token.bin");
}

function getAppSession() {
  return session.fromPartition(APP_SESSION_PARTITION);
}

function readEnvValue(envFilePath, key) {
  if (!fs.existsSync(envFilePath)) {
    return null;
  }

  const keyPattern = new RegExp(`^\\s*${key}\\s*=\\s*(.*)\\s*$`);
  const lines = fs.readFileSync(envFilePath, "utf8").split(/\r?\n/);
  for (const line of lines) {
    if (!line.trim() || line.trimStart().startsWith("#")) {
      continue;
    }
    const match = line.match(keyPattern);
    if (!match) {
      continue;
    }
    const rawValue = match[1].trim();
    if (
      (rawValue.startsWith("\"") && rawValue.endsWith("\"")) ||
      (rawValue.startsWith("'") && rawValue.endsWith("'"))
    ) {
      return rawValue.slice(1, -1);
    }
    return rawValue;
  }
  return null;
}

function removeEnvValue(envFilePath, key) {
  if (!fs.existsSync(envFilePath)) {
    return;
  }

  const keyPattern = new RegExp(`^\\s*${key}\\s*=`);
  const lines = fs.readFileSync(envFilePath, "utf8").split(/\r?\n/);
  const filteredLines = lines.filter((line) => !keyPattern.test(line));
  fs.writeFileSync(envFilePath, filteredLines.join("\n"), "utf8");
}

function ensureSafeStorageAvailable() {
  if (!safeStorage.isEncryptionAvailable()) {
    throw new Error("Secure credential storage is not available on this machine.");
  }
}

function storeEncryptedJiraToken(token) {
  ensureSafeStorageAvailable();
  const tokenPath = getEncryptedJiraTokenPath();
  fs.mkdirSync(path.dirname(tokenPath), { recursive: true });
  fs.writeFileSync(tokenPath, safeStorage.encryptString(token).toString("base64"), "utf8");
}

function storeJiraTokenFromRenderer(token) {
  const normalizedToken = typeof token === "string" ? token.trim() : "";
  if (!normalizedToken) {
    throw new Error("Jira API token is required.");
  }
  storeEncryptedJiraToken(normalizedToken);
  return { ok: true };
}

function readEncryptedJiraToken() {
  const tokenPath = getEncryptedJiraTokenPath();
  if (!fs.existsSync(tokenPath)) {
    return null;
  }

  ensureSafeStorageAvailable();
  const encryptedValue = fs.readFileSync(tokenPath, "utf8").trim();
  if (!encryptedValue) {
    return null;
  }
  return safeStorage.decryptString(Buffer.from(encryptedValue, "base64"));
}

function getJiraTokenForBackend(envFilePath) {
  const encryptedToken = readEncryptedJiraToken();
  if (encryptedToken) {
    return encryptedToken;
  }

  const plaintextToken = readEnvValue(envFilePath, "JIRA_API_TOKEN");
  if (!plaintextToken) {
    return null;
  }
  storeEncryptedJiraToken(plaintextToken);
  removeEnvValue(envFilePath, "JIRA_API_TOKEN");
  return plaintextToken;
}

function copyLegacyDatabase(databasePath) {
  if (app.isPackaged || fs.existsSync(databasePath)) {
    return;
  }

  const legacyDatabasePath = path.resolve(__dirname, "../../backend/data/lighthouse.db");
  if (fs.existsSync(legacyDatabasePath)) {
    fs.copyFileSync(legacyDatabasePath, databasePath);
  }
}

function findAvailablePort() {
  return new Promise((resolve, reject) => {
    const server = net.createServer();
    server.unref();
    server.once("error", reject);
    server.listen(0, LOOPBACK_HOST, () => {
      const address = server.address();
      if (!address || typeof address === "string") {
        server.close();
        reject(new Error("Could not determine an available backend port."));
        return;
      }
      const { port } = address;
      server.close((error) => {
        if (error) {
          reject(error);
          return;
        }
        resolve(port);
      });
    });
  });
}

function checkBackendHealth(origin) {
  return new Promise((resolve) => {
    const request = http.get(`${origin}/health`, (response) => {
      response.resume();
      resolve(response.statusCode === 200);
    });
    request.setTimeout(1000, () => {
      request.destroy();
      resolve(false);
    });
    request.on("error", () => resolve(false));
  });
}

async function waitForBackend(origin, logPath) {
  const deadline = Date.now() + BACKEND_STARTUP_TIMEOUT_MS;
  while (Date.now() < deadline) {
    if (!backendProcess || backendProcess.exitCode !== null) {
      throw new Error(`The local backend exited during startup. See ${logPath}`);
    }
    if (await checkBackendHealth(origin)) {
      return;
    }
    await new Promise((resolve) => setTimeout(resolve, BACKEND_HEALTH_RETRY_MS));
  }
  throw new Error(`The local backend did not become ready. See ${logPath}`);
}

function requestBackendJson(backendPath) {
  if (!backendOrigin || !localApiToken) {
    return Promise.reject(new Error("The authenticated local backend is unavailable."));
  }
  return new Promise((resolve, reject) => {
    let settled = false;
    const finish = (callback, value) => {
      if (settled) {
        return;
      }
      settled = true;
      callback(value);
    };
    const request = http.get(
      `${backendOrigin}${backendPath}`,
      { headers: { Authorization: `Bearer ${localApiToken}` } },
      (response) => {
        response.setEncoding("utf8");
        let body = "";
        response.on("data", (chunk) => {
          body += chunk;
          if (body.length > 1024 * 1024) {
            response.destroy(new Error(`Backend verification response is too large: ${backendPath}`));
          }
        });
        response.on("error", (error) => finish(reject, error));
        response.on("end", () => {
          if (response.statusCode !== 200) {
            finish(reject, new Error(`Backend verification failed for ${backendPath}: HTTP ${response.statusCode}`));
            return;
          }
          try {
            finish(resolve, JSON.parse(body));
          } catch {
            finish(reject, new Error(`Backend verification returned invalid JSON for ${backendPath}`));
          }
        });
      },
    );
    request.setTimeout(3000, () => {
      request.destroy(new Error(`Backend verification timed out for ${backendPath}`));
    });
    request.on("error", (error) => finish(reject, error));
  });
}

function validateCollectionResponse(collectionName, payload) {
  if (
    !payload ||
    typeof payload !== "object" ||
    !Array.isArray(payload.items) ||
    !Number.isSafeInteger(payload.total) ||
    payload.total < 0
  ) {
    throw new Error(`${collectionName} API did not return its structured collection contract.`);
  }
}

async function getVerifiedCoreCollections() {
  const releases = await requestBackendJson("/releases?skip=0&limit=1");
  validateCollectionResponse("Releases", releases);
  const sprints = await requestBackendJson("/sprints?skip=0&limit=1");
  validateCollectionResponse("Sprints", sprints);
  return { releases, sprints };
}

async function verifyRestoredBackendState() {
  await getVerifiedCoreCollections();
}

async function verifyEmptyBackendState() {
  const { releases, sprints } = await getVerifiedCoreCollections();
  if (releases.total !== 0 || releases.items.length !== 0) {
    throw new Error("Releases API is not empty after local data removal.");
  }
  if (sprints.total !== 0 || sprints.items.length !== 0) {
    throw new Error("Sprints API is not empty after local data removal.");
  }
}

async function verifyFactoryResetState() {
  await verifyEmptyBackendState();
  const configuration = await requestBackendJson("/config/jira");
  if (
    !configuration ||
    typeof configuration !== "object" ||
    configuration.is_complete !== false ||
    configuration.jira_api_token_configured !== false
  ) {
    throw new Error("Jira configuration did not return to first-run state after Factory Reset.");
  }
}

async function startBackend() {
  const executablePath = getBackendExecutable();
  if (!fs.existsSync(executablePath)) {
    throw new Error(`Packaged backend not found at ${executablePath}. Run npm run build:backend first.`);
  }

  const paths = getDesktopDataPaths();
  const dataDirectory = paths.dataDirectory;
  const logsDirectory = paths.logsDirectory;
  const databasePath = paths.databasePath;
  const logPath = path.join(logsDirectory, "backend.log");
  fs.mkdirSync(dataDirectory, { recursive: true });
  fs.mkdirSync(logsDirectory, { recursive: true });
  rotateBackendLogIfNeeded(logPath);
  copyLegacyDatabase(databasePath);

  const port = DEV_RENDERER_URL ? DEV_BACKEND_PORT : await findAvailablePort();
  backendOrigin = `http://${LOOPBACK_HOST}:${port}`;
  const args = [
    "--host",
    LOOPBACK_HOST,
    "--port",
    String(port),
    "--database-path",
    databasePath,
    "--app-env",
    app.isPackaged ? "prod" : "dev",
    "--log-level",
    "info",
  ];
  const envFile = getBackendEnvFile();
  if (envFile) {
    args.push("--env-file", envFile);
  }

  localApiToken = crypto.randomBytes(32).toString("hex");
  const jiraToken = getJiraTokenForBackend(envFile);
  const childEnvironment = { ...process.env };
  delete childEnvironment.ELECTRON_RUN_AS_NODE;
  childEnvironment.LIGHTHOUSE_API_TOKEN = localApiToken;
  if (jiraToken) {
    childEnvironment.JIRA_API_TOKEN = jiraToken;
  } else if (app.isPackaged) {
    delete childEnvironment.JIRA_API_TOKEN;
  }

  const logDescriptor = fs.openSync(logPath, "a");
  try {
    backendProcess = spawn(executablePath, args, {
      env: childEnvironment,
      stdio: ["ignore", logDescriptor, logDescriptor],
      windowsHide: true,
    });
  } finally {
    fs.closeSync(logDescriptor);
  }

  const spawnedBackendProcess = backendProcess;
  spawnedBackendProcess.once("error", (error) => {
    if (!isQuitting && !intentionallyStoppedBackendProcesses.has(spawnedBackendProcess)) {
      showBackendErrorScreen(`The local backend could not start: ${error.message}`, `Log: ${logPath}`);
    }
  });
  spawnedBackendProcess.once("exit", (code) => {
    const wasIntentionallyStopped = intentionallyStoppedBackendProcesses.has(spawnedBackendProcess);
    intentionallyStoppedBackendProcesses.delete(spawnedBackendProcess);
    if (backendProcess === spawnedBackendProcess) {
      backendProcess = null;
    }
    if (!isQuitting && !wasIntentionallyStopped) {
      showBackendErrorScreen(`The local backend exited with code ${code ?? "unknown"}.`, `Log: ${logPath}`);
    }
  });

  await waitForBackend(backendOrigin, logPath);
}

async function stopBackend() {
  const processToStop = backendProcess;
  if (!processToStop || processToStop.exitCode !== null) {
    if (backendProcess === processToStop) {
      backendProcess = null;
    }
    return;
  }

  intentionallyStoppedBackendProcesses.add(processToStop);
  try {
    await stopProcessAndWait(processToStop, BACKEND_SHUTDOWN_TIMEOUT_MS);
  } catch (error) {
    intentionallyStoppedBackendProcesses.delete(processToStop);
    throw error;
  }
  intentionallyStoppedBackendProcesses.delete(processToStop);
  if (backendProcess === processToStop) {
    backendProcess = null;
  }
}

async function restartBackend() {
  await stopBackend();
  await startBackend();
}

function fileSize(filePath) {
  try {
    return fs.statSync(filePath).size;
  } catch {
    return 0;
  }
}

function directorySize(directoryPath) {
  if (!fs.existsSync(directoryPath)) {
    return 0;
  }

  let totalBytes = 0;
  for (const entry of fs.readdirSync(directoryPath, { withFileTypes: true })) {
    const entryPath = path.join(directoryPath, entry.name);
    if (entry.isDirectory()) {
      totalBytes += directorySize(entryPath);
    } else if (entry.isFile()) {
      totalBytes += fileSize(entryPath);
    }
  }
  return totalBytes;
}

function deleteIfExists(targetPath) {
  fs.rmSync(targetPath, { recursive: true, force: true });
}

function rotatedLogName() {
  return `backend-${timestampForBackup()}.log`;
}

function pruneBackendLogs(logsDirectory) {
  if (!fs.existsSync(logsDirectory)) {
    return;
  }

  const retentionCutoff = Date.now() - BACKEND_LOG_RETENTION_DAYS * 24 * 60 * 60 * 1000;
  const rotatedLogs = fs
    .readdirSync(logsDirectory, { withFileTypes: true })
    .filter((entry) => entry.isFile() && /^backend-.+\.log$/.test(entry.name))
    .map((entry) => {
      const filePath = path.join(logsDirectory, entry.name);
      return { filePath, mtimeMs: fs.statSync(filePath).mtimeMs };
    })
    .sort((left, right) => right.mtimeMs - left.mtimeMs);

  for (const logFile of rotatedLogs) {
    if (logFile.mtimeMs < retentionCutoff) {
      deleteIfExists(logFile.filePath);
    }
  }

  rotatedLogs.slice(BACKEND_LOG_MAX_FILES).forEach((logFile) => deleteIfExists(logFile.filePath));
}

function rotateBackendLogIfNeeded(logPath) {
  const logsDirectory = path.dirname(logPath);
  fs.mkdirSync(logsDirectory, { recursive: true });
  pruneBackendLogs(logsDirectory);
  if (!fs.existsSync(logPath) || fileSize(logPath) <= BACKEND_LOG_MAX_BYTES) {
    return;
  }

  fs.renameSync(logPath, path.join(logsDirectory, rotatedLogName()));
  pruneBackendLogs(logsDirectory);
}

function copyIfExists(sourcePath, targetPath) {
  if (!fs.existsSync(sourcePath)) {
    return false;
  }
  fs.mkdirSync(path.dirname(targetPath), { recursive: true });
  fs.copyFileSync(sourcePath, targetPath);
  return true;
}

function runBackendUtility(args) {
  const executablePath = getBackendExecutable();
  if (!fs.existsSync(executablePath)) {
    throw new Error(`Packaged backend not found at ${executablePath}. Run npm run build:backend first.`);
  }
  const childEnvironment = { ...process.env };
  delete childEnvironment.ELECTRON_RUN_AS_NODE;
  const result = spawnSync(executablePath, args, {
    encoding: "utf8",
    env: childEnvironment,
    maxBuffer: 1024 * 1024,
    windowsHide: true,
  });
  if (result.error) {
    throw result.error;
  }
  const outputLines = String(result.stdout ?? "")
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean);
  let report;
  try {
    report = JSON.parse(outputLines.at(-1) ?? "");
  } catch {
    throw new Error(`Backup utility returned an invalid response: ${String(result.stderr ?? "").trim()}`);
  }
  if (result.status !== 0 || report.valid !== true) {
    const pathLabel = report.path ? ` (${report.path})` : "";
    throw new Error(`${report.rule ?? "backup_validation"}: ${report.detail ?? "validation failed"}${pathLabel}`);
  }
  return report;
}

function validateEncryptedTokenFile(tokenPath) {
  if (!safeStorage.isEncryptionAvailable()) {
    throw new Error("Encrypted-token validation is unavailable for the current operating-system account.");
  }
  const encodedToken = fs.readFileSync(tokenPath, "utf8").trim();
  const encryptedToken = Buffer.from(encodedToken, "base64");
  if (!encodedToken || encryptedToken.length === 0 || encryptedToken.toString("base64") !== encodedToken) {
    throw new Error("Encrypted token is not valid base64 data.");
  }
  const decryptedToken = safeStorage.decryptString(encryptedToken);
  if (!decryptedToken.trim()) {
    throw new Error("Encrypted token is empty.");
  }
  return { valid: true };
}

function validateDesktopBackup(backupDirectory) {
  return validateSettingsBackup(backupDirectory, {
    validateDatabase: (databasePath) =>
      runBackendUtility(["--validate-sqlite-backup", databasePath]),
    validateConfig: (configPath) => runBackendUtility(["--validate-env-file", configPath]),
    validateToken: (tokenPath) => validateEncryptedTokenFile(tokenPath),
  });
}

function buildSettingsRestorePlan(validatedBackup, paths) {
  const activePathMap = new Map();
  const deletePaths = [];
  const replacements = [];
  const addActivePath = (relativePath, activePath) => {
    activePathMap.set(relativePath, activePath);
  };

  if (validatedBackup.payloadPaths[BACKUP_DATABASE_PATH]) {
    addActivePath(BACKUP_DATABASE_PATH, paths.databasePath);
    addActivePath(RECOVERY_DATABASE_WAL_PATH, `${paths.databasePath}-wal`);
    addActivePath(RECOVERY_DATABASE_SHM_PATH, `${paths.databasePath}-shm`);
    deletePaths.push(paths.databasePath, `${paths.databasePath}-wal`, `${paths.databasePath}-shm`);
    replacements.push({
      sourcePath: validatedBackup.payloadPaths[BACKUP_DATABASE_PATH],
      targetPath: paths.databasePath,
    });
  }
  if (validatedBackup.payloadPaths[BACKUP_CONFIG_PATH]) {
    addActivePath(BACKUP_CONFIG_PATH, paths.configPath);
    replacements.push({
      sourcePath: validatedBackup.payloadPaths[BACKUP_CONFIG_PATH],
      targetPath: paths.configPath,
    });
  }
  if (validatedBackup.payloadPaths[BACKUP_TOKEN_PATH]) {
    addActivePath(BACKUP_TOKEN_PATH, paths.tokenPath);
    replacements.push({
      sourcePath: validatedBackup.payloadPaths[BACKUP_TOKEN_PATH],
      targetPath: paths.tokenPath,
    });
  }

  return {
    activePaths: [...activePathMap].map(([relativePath, activePath]) => ({
      relativePath,
      activePath,
      ...(relativePath === BACKUP_CONFIG_PATH
        ? { targetLocation: paths.configLocation }
        : {}),
    })),
    applyChanges: () => applyFileReplacementPlan({ deletePaths, replacements }),
    resolveActivePath: (relativePath) => {
      const activePath = activePathMap.get(relativePath);
      if (!activePath) {
        throw new Error(`Restore recovery path is not mapped: ${relativePath}`);
      }
      return activePath;
    },
  };
}

function databaseRecoveryPathMap(paths) {
  return new Map([
    [BACKUP_DATABASE_PATH, paths.databasePath],
    [RECOVERY_DATABASE_WAL_PATH, `${paths.databasePath}-wal`],
    [RECOVERY_DATABASE_SHM_PATH, `${paths.databasePath}-shm`],
  ]);
}

function buildClearDataPlan(paths) {
  const activePathMap = databaseRecoveryPathMap(paths);
  const deletePaths = [...activePathMap.values()];
  return {
    activePaths: [...activePathMap].map(([relativePath, activePath]) => ({ relativePath, activePath })),
    applyChanges: () => applyFileReplacementPlan({ deletePaths }),
    resolveActivePath: (relativePath) => {
      const activePath = activePathMap.get(relativePath);
      if (!activePath) {
        throw new Error(`Clear Data recovery path is not mapped: ${relativePath}`);
      }
      return activePath;
    },
  };
}

function buildFactoryResetPlan(paths) {
  const activePathMap = databaseRecoveryPathMap(paths);
  activePathMap.set(BACKUP_CONFIG_PATH, paths.configPath);
  activePathMap.set(BACKUP_TOKEN_PATH, paths.tokenPath);
  activePathMap.set("logs", paths.logsDirectory);
  const deletePaths = [...activePathMap.values()];
  return {
    activePaths: [...activePathMap].map(([relativePath, activePath]) => ({
      relativePath,
      activePath,
      ...(relativePath === BACKUP_CONFIG_PATH
        ? { targetLocation: paths.configLocation }
        : {}),
    })),
    applyChanges: () => applyFileReplacementPlan({ deletePaths }),
    resolveActivePath: (relativePath) => {
      const activePath = activePathMap.get(relativePath);
      if (activePath) {
        return activePath;
      }
      if (relativePath.startsWith("logs/")) {
        return path.join(paths.logsDirectory, ...relativePath.slice("logs/".length).split("/"));
      }
      throw new Error(`Factory Reset recovery path is not mapped: ${relativePath}`);
    },
  };
}

function resolveStartupRecoveryPath(paths, relativePath, targetLocation) {
  if (relativePath === BACKUP_CONFIG_PATH) {
    if (targetLocation === TARGET_LOCATION_USER_DATA) {
      return paths.userConfigPath;
    }
    if (targetLocation === TARGET_LOCATION_APPLICATION_SIDECAR) {
      return paths.sidecarConfigPath;
    }
    throw new Error(`Startup recovery target location is not supported: ${targetLocation}`);
  }
  if (targetLocation !== TARGET_LOCATION_USER_DATA) {
    throw new Error(`Startup recovery target location is invalid for ${relativePath}: ${targetLocation}`);
  }
  const activePathMap = databaseRecoveryPathMap(paths);
  activePathMap.set(BACKUP_TOKEN_PATH, paths.tokenPath);
  activePathMap.set("logs", paths.logsDirectory);
  const activePath = activePathMap.get(relativePath);
  if (activePath) {
    return activePath;
  }
  if (relativePath.startsWith("logs/")) {
    return path.join(paths.logsDirectory, ...relativePath.slice("logs/".length).split("/"));
  }
  throw new Error(`Startup recovery path is not mapped: ${relativePath}`);
}

async function recoverDesktopStorageAtStartup() {
  const paths = getDesktopDataPaths();
  return recoverInterruptedStorageOperation({
    recoveryRoot: path.join(paths.userDataDirectory, "recovery"),
    resolveActivePath: (relativePath, targetLocation) =>
      resolveStartupRecoveryPath(paths, relativePath, targetLocation),
    startBackend,
    stopBackend,
    verifyState: verifyRestoredBackendState,
  });
}

function captureFactoryResetFailure(journalDirectory, paths) {
  const backendLogPath = path.join(paths.logsDirectory, "backend.log");
  if (fs.existsSync(backendLogPath)) {
    replaceFileAtomically(backendLogPath, path.join(journalDirectory, "failed-backend.log"));
  }
}

function preserveFactoryResetFailure(journalDirectory, operationId, paths) {
  fs.mkdirSync(paths.logsDirectory, { recursive: true });
  const diagnosticPrefix = `factory-reset-${operationId}-failure`;
  replaceFileAtomically(
    path.join(journalDirectory, "failure.json"),
    path.join(paths.logsDirectory, `${diagnosticPrefix}.json`),
  );
  const failedBackendLog = path.join(journalDirectory, "failed-backend.log");
  if (fs.existsSync(failedBackendLog)) {
    replaceFileAtomically(failedBackendLog, path.join(paths.logsDirectory, `${diagnosticPrefix}.log`));
  }
}

async function handleStorageTransactionFailure(error, operationLabel) {
  if (error instanceof StorageTransactionError && error.recoveryRequired) {
    const recoveryDetail = error.recoveryPath ? `Recovery: ${error.recoveryPath}` : "Recovery requires diagnosis.";
    showBackendErrorScreen(`LighthousePM could not complete ${operationLabel}.`, `${error.message}\n${recoveryDetail}`);
  } else if (error instanceof StorageTransactionError && error.previousStateRestored && rendererOrigin && mainWindow) {
    try {
      await mainWindow.loadURL(rendererOrigin);
    } catch (workspaceError) {
      showBackendErrorScreen(
        "LighthousePM restored the previous backend but could not reopen the workspace.",
        workspaceError instanceof Error ? workspaceError.message : "Unknown workspace error",
      );
    }
  }
}

function timestampForBackup() {
  return new Date().toISOString().replace(/[:.]/g, "-");
}

function getDesktopStorageInfo() {
  const paths = getDesktopDataPaths();
  const databaseBytes = fileSize(paths.databasePath);
  const configBytes = fileSize(paths.configPath);
  const tokenBytes = fileSize(paths.tokenPath);
  const logsBytes = directorySize(paths.logsDirectory);
  return {
    isElectron: true,
    backendOrigin,
    paths,
    usage: {
      databaseBytes,
      configBytes,
      tokenBytes,
      logsBytes,
      totalBytes: databaseBytes + configBytes + tokenBytes + logsBytes,
    },
    exists: {
      database: fs.existsSync(paths.databasePath),
      config: fs.existsSync(paths.configPath),
      encryptedToken: fs.existsSync(paths.tokenPath),
    },
  };
}

async function createDesktopBackup() {
  const result = await dialog.showOpenDialog(mainWindow ?? undefined, {
    title: "Choose Backup Location",
    properties: ["openDirectory", "createDirectory"],
  });
  if (result.canceled || result.filePaths.length === 0) {
    return { ok: false, message: "Backup cancelled." };
  }

  const paths = getDesktopDataPaths();
  const backupDirectory = path.join(result.filePaths[0], `lighthousepm-backup-${timestampForBackup()}`);
  fs.mkdirSync(backupDirectory, { recursive: true });

  const relativePaths = [];
  let databaseValidation = null;
  if (fs.existsSync(paths.databasePath)) {
    const databaseTarget = path.join(backupDirectory, ...BACKUP_DATABASE_PATH.split("/"));
    databaseValidation = runBackendUtility([
      "--create-sqlite-backup",
      paths.databasePath,
      "--output-path",
      databaseTarget,
    ]);
    relativePaths.push(BACKUP_DATABASE_PATH);
  }
  if (copyIfExists(paths.configPath, path.join(backupDirectory, BACKUP_CONFIG_PATH))) {
    runBackendUtility(["--validate-env-file", path.join(backupDirectory, BACKUP_CONFIG_PATH)]);
    relativePaths.push(BACKUP_CONFIG_PATH);
  }
  if (copyIfExists(paths.tokenPath, path.join(backupDirectory, ...BACKUP_TOKEN_PATH.split("/")))) {
    validateEncryptedTokenFile(path.join(backupDirectory, ...BACKUP_TOKEN_PATH.split("/")));
    relativePaths.push(BACKUP_TOKEN_PATH);
  }

  publishValidatedSettingsBackup(
    backupDirectory,
    relativePaths,
    databaseValidation,
    validateDesktopBackup,
  );
  return { ok: true, message: "Backup created.", path: backupDirectory };
}

function resolveBackupDirectory(selectedPath) {
  const manifestPath = path.join(selectedPath, "manifest.json");
  if (fs.existsSync(manifestPath)) {
    return selectedPath;
  }
  const childDirectories = fs
    .readdirSync(selectedPath, { withFileTypes: true })
    .filter((entry) => entry.isDirectory() && entry.name.startsWith("lighthousepm-backup-"))
    .map((entry) => path.join(selectedPath, entry.name));
  const newestBackup = childDirectories
    .filter((directoryPath) => fs.existsSync(path.join(directoryPath, "manifest.json")))
    .sort()
    .at(-1);
  if (newestBackup) {
    return newestBackup;
  }
  throw new Error("Selected folder does not contain a LighthousePM backup.");
}

async function restoreDesktopBackup() {
  const result = await dialog.showOpenDialog(mainWindow ?? undefined, {
    title: "Choose LighthousePM Backup Folder",
    properties: ["openDirectory"],
  });
  if (result.canceled || result.filePaths.length === 0) {
    return { ok: false, message: "Restore cancelled." };
  }

  const backupDirectory = resolveBackupDirectory(result.filePaths[0]);
  const validatedBackup = validateDesktopBackup(backupDirectory);
  const paths = getDesktopDataPaths();
  const restorePlan = buildSettingsRestorePlan(validatedBackup, paths);
  try {
    await runStorageTransaction({
      operation: "restore",
      operationId: crypto.randomUUID(),
      operationLabel: "Restore",
      recoveryRoot: path.join(paths.userDataDirectory, "recovery"),
      activePaths: restorePlan.activePaths,
      applyChanges: restorePlan.applyChanges,
      resolveActivePath: restorePlan.resolveActivePath,
      startBackend,
      stopBackend,
      verifyState: verifyRestoredBackendState,
    });
  } catch (error) {
    await handleStorageTransactionFailure(error, "Settings Restore");
    throw error;
  }
  return { ok: true, message: "Backup restored.", path: backupDirectory };
}

async function clearDesktopData() {
  const paths = getDesktopDataPaths();
  const clearPlan = buildClearDataPlan(paths);
  try {
    await runStorageTransaction({
      operation: "clear-data",
      operationId: crypto.randomUUID(),
      operationLabel: "Clear Data",
      recoveryRoot: path.join(paths.userDataDirectory, "recovery"),
      activePaths: clearPlan.activePaths,
      applyChanges: clearPlan.applyChanges,
      resolveActivePath: clearPlan.resolveActivePath,
      startBackend,
      stopBackend,
      verifyState: verifyEmptyBackendState,
    });
  } catch (error) {
    await handleStorageTransactionFailure(error, "Clear Data");
    throw error;
  }
  return { ok: true, message: "Local synced data cleared." };
}

async function factoryResetDesktopData() {
  const paths = getDesktopDataPaths();
  const factoryResetPlan = buildFactoryResetPlan(paths);
  const operationId = crypto.randomUUID();
  try {
    await runStorageTransaction({
      operation: "factory-reset",
      operationId,
      operationLabel: "Factory Reset",
      recoveryRoot: path.join(paths.userDataDirectory, "recovery"),
      activePaths: factoryResetPlan.activePaths,
      applyChanges: factoryResetPlan.applyChanges,
      resolveActivePath: factoryResetPlan.resolveActivePath,
      startBackend,
      stopBackend,
      verifyState: verifyFactoryResetState,
      captureOperationDiagnostic: (journalDirectory) => captureFactoryResetFailure(journalDirectory, paths),
      preserveRollbackDiagnostic: (journalDirectory) =>
        preserveFactoryResetFailure(journalDirectory, operationId, paths),
    });
  } catch (error) {
    await handleStorageTransactionFailure(error, "Factory Reset");
    throw error;
  }
  return { ok: true, message: "Factory reset complete." };
}

async function revealDesktopDataFolder() {
  const paths = getDesktopDataPaths();
  fs.mkdirSync(paths.userDataDirectory, { recursive: true });
  const errorMessage = await shell.openPath(paths.userDataDirectory);
  if (errorMessage) {
    throw new Error(errorMessage);
  }
  return { ok: true, path: paths.userDataDirectory };
}

function safePdfFilename(filename) {
  const fallbackName = "lighthousepm-report.pdf";
  const basename = path.basename(typeof filename === "string" ? filename : fallbackName);
  const normalized = basename.replace(/[<>:"/\\|?*\x00-\x1F]/g, "-").replace(/-+/g, "-").trim();
  if (!normalized || normalized === ".pdf") {
    return fallbackName;
  }
  return normalized.toLowerCase().endsWith(".pdf") ? normalized : `${normalized}.pdf`;
}

async function savePdfFromRenderer({ filename, data }) {
  const safeFilename = safePdfFilename(filename);
  const bytes = Buffer.from(data instanceof Uint8Array ? data : new Uint8Array(data));
  if (bytes.length === 0) {
    throw new Error("PDF export was empty.");
  }

  const result = await dialog.showSaveDialog(mainWindow ?? undefined, {
    title: "Save PDF Report",
    defaultPath: path.join(app.getPath("documents"), safeFilename),
    filters: [{ name: "PDF Documents", extensions: ["pdf"] }],
  });
  if (result.canceled || !result.filePath) {
    return { ok: false, message: "Save cancelled." };
  }

  fs.writeFileSync(result.filePath, bytes);
  return { ok: true, message: "PDF saved.", path: result.filePath };
}

function resolveRendererFile(rendererDirectory, requestUrl) {
  const pathname = decodeURIComponent(new URL(requestUrl, "http://127.0.0.1").pathname);
  const relativePath = pathname === "/" ? "index.html" : pathname.replace(/^\/+/, "");
  const requestedPath = path.resolve(rendererDirectory, relativePath);
  const rendererRoot = `${path.resolve(rendererDirectory)}${path.sep}`;

  if (requestedPath !== path.resolve(rendererDirectory) && !requestedPath.startsWith(rendererRoot)) {
    return null;
  }
  return requestedPath;
}

function writeSecurityHeaders(response) {
  response.setHeader(
    "Content-Security-Policy",
    [
      "default-src 'self'",
      "script-src 'self'",
      "style-src 'self' 'unsafe-inline'",
      "img-src 'self' data:",
      "font-src 'self' data:",
      "connect-src 'self'",
      "object-src 'none'",
      "base-uri 'self'",
      "frame-ancestors 'none'",
      "form-action 'self'",
    ].join("; "),
  );
  response.setHeader("Referrer-Policy", "no-referrer");
  response.setHeader("X-Content-Type-Options", "nosniff");
  response.setHeader("Cache-Control", "no-store");
}

function serveFile(response, filePath) {
  const contentType = CONTENT_TYPES.get(path.extname(filePath).toLowerCase()) ?? "application/octet-stream";
  response.statusCode = 200;
  response.setHeader("Content-Type", contentType);
  writeSecurityHeaders(response);
  fs.createReadStream(filePath).pipe(response);
}

function proxyApiRequest(request, response) {
  if (!backendOrigin) {
    response.statusCode = 503;
    response.setHeader("Content-Type", "application/json; charset=utf-8");
    response.setHeader("Cache-Control", "no-store");
    response.end(JSON.stringify({ detail: "The local LighthousePM backend is starting." }));
    return;
  }

  const requestUrl = new URL(request.url ?? "/api", "http://127.0.0.1");
  const backendPath = `${requestUrl.pathname.replace(/^\/api/, "") || "/"}${requestUrl.search}`;
  const headers = {
    ...request.headers,
    authorization: `Bearer ${localApiToken}`,
    host: new URL(backendOrigin).host,
  };
  delete headers.origin;
  delete headers.referer;

  const proxyRequest = http.request(
    `${backendOrigin}${backendPath}`,
    {
      method: request.method,
      headers,
    },
    (proxyResponse) => {
      response.writeHead(proxyResponse.statusCode ?? 502, {
        ...proxyResponse.headers,
        "cache-control": "no-store",
      });
      proxyResponse.pipe(response);
    },
  );

  proxyRequest.on("error", () => {
    if (response.headersSent) {
      response.destroy();
      return;
    }
    response.statusCode = 502;
    response.setHeader("Content-Type", "application/json; charset=utf-8");
    response.setHeader("Cache-Control", "no-store");
    response.end(JSON.stringify({ detail: "Could not reach the local LighthousePM backend." }));
  });

  if (request.method === "PUT" && backendPath.split("?")[0] === "/config/jira") {
    readRequestBody(request)
      .then((body) => {
        maybeStoreJiraTokenFromConfigBody(body);
        proxyRequest.end(body);
      })
      .catch((error) => {
        proxyRequest.destroy();
        writeJsonError(response, 400, error.message);
      });
    return;
  }

  request.pipe(proxyRequest);
}

function readRequestBody(request) {
  return new Promise((resolve, reject) => {
    const chunks = [];
    let byteLength = 0;
    request.on("data", (chunk) => {
      byteLength += chunk.length;
      if (byteLength > 1024 * 1024) {
        reject(new Error("Request body is too large."));
        request.destroy();
        return;
      }
      chunks.push(chunk);
    });
    request.on("end", () => resolve(Buffer.concat(chunks)));
    request.on("error", reject);
  });
}

function maybeStoreJiraTokenFromConfigBody(body) {
  if (body.length === 0) {
    return;
  }

  const payload = JSON.parse(body.toString("utf8"));
  const token = typeof payload.jira_api_token === "string" ? payload.jira_api_token.trim() : "";
  if (token) {
    storeEncryptedJiraToken(token);
  }
}

function writeJsonError(response, statusCode, detail) {
  if (response.headersSent) {
    response.destroy();
    return;
  }
  response.statusCode = statusCode;
  response.setHeader("Content-Type", "application/json; charset=utf-8");
  response.setHeader("Cache-Control", "no-store");
  response.end(JSON.stringify({ detail }));
}

function startRendererServer() {
  const rendererDirectory = getRendererDirectory();
  const indexPath = path.join(rendererDirectory, "index.html");

  if (!fs.existsSync(indexPath)) {
    throw new Error(`Frontend build not found at ${indexPath}. Run npm run build:frontend first.`);
  }

  return new Promise((resolve, reject) => {
    const server = http.createServer((request, response) => {
      try {
        const requestUrl = new URL(request.url ?? "/", "http://127.0.0.1");
        if (requestUrl.pathname === "/api" || requestUrl.pathname.startsWith("/api/")) {
          proxyApiRequest(request, response);
          return;
        }

        const requestedPath = resolveRendererFile(rendererDirectory, request.url ?? "/");
        if (!requestedPath) {
          response.statusCode = 403;
          response.end("Forbidden");
          return;
        }

        fs.stat(requestedPath, (error, stats) => {
          if (!error && stats.isFile()) {
            serveFile(response, requestedPath);
            return;
          }
          serveFile(response, indexPath);
        });
      } catch {
        response.statusCode = 400;
        response.end("Bad request");
      }
    });

    server.once("error", reject);
    server.listen(0, LOOPBACK_HOST, () => {
      server.removeListener("error", reject);
      rendererServer = server;
      const address = server.address();
      if (!address || typeof address === "string") {
        reject(new Error("Could not determine the desktop renderer address."));
        return;
      }
      resolve(`http://${LOOPBACK_HOST}:${address.port}`);
    });
  });
}

function getDevRendererOrigin() {
  if (!DEV_RENDERER_URL) {
    return null;
  }

  const parsedUrl = new URL(DEV_RENDERER_URL);
  if (parsedUrl.origin !== DEV_RENDERER_ORIGIN) {
    throw new Error(`ELECTRON_RENDERER_URL must be ${DEV_RENDERER_ORIGIN}`);
  }
  return parsedUrl.origin;
}

function isAllowedAppNavigation(targetUrl) {
  try {
    return new URL(targetUrl).origin === rendererOrigin;
  } catch {
    return false;
  }
}

function openExternalUrl(targetUrl) {
  try {
    const parsedUrl = new URL(targetUrl);
    if (parsedUrl.protocol === "https:") {
      void shell.openExternal(parsedUrl.toString());
      return { ok: true };
    }
  } catch {
    // Invalid external URLs are ignored.
  }
  return { ok: false, message: "Only HTTPS links can be opened externally." };
}

function escapeHtml(value) {
  return String(value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function desktopStatusDocument({ title, heading, message, detail }) {
  return `<!doctype html>
<html>
  <head>
    <meta charset="utf-8" />
    <meta name="color-scheme" content="light" />
    <title>${escapeHtml(title)}</title>
    <style>
      body {
        margin: 0;
        min-height: 100vh;
        display: grid;
        place-items: center;
        background: #f4f7fb;
        color: #101733;
        font-family: Inter, Segoe UI, Arial, sans-serif;
      }
      main {
        width: min(560px, calc(100vw - 48px));
        display: grid;
        gap: 14px;
      }
      h1 {
        margin: 0;
        font-size: 1.45rem;
      }
      p {
        margin: 0;
        color: #52617f;
        line-height: 1.5;
      }
      code {
        display: block;
        padding: 12px;
        border: 1px solid #d9deec;
        border-radius: 8px;
        background: #ffffff;
        color: #344468;
        overflow-wrap: anywhere;
      }
    </style>
  </head>
  <body>
    <main>
      <h1>${escapeHtml(heading)}</h1>
      <p>${escapeHtml(message)}</p>
      ${detail ? `<code>${escapeHtml(detail)}</code>` : ""}
    </main>
  </body>
</html>`;
}

function desktopStatusUrl(options) {
  return `data:text/html;charset=utf-8,${encodeURIComponent(desktopStatusDocument(options))}`;
}

function startupScreenUrl() {
  return desktopStatusUrl({
    title: "LighthousePM Starting",
    heading: "Starting LighthousePM",
    message: "Preparing the local backend and loading your dashboard.",
  });
}

function backendErrorScreenUrl(message, detail) {
  return desktopStatusUrl({
    title: "LighthousePM Backend Error",
    heading: "The local backend stopped",
    message,
    detail,
  });
}

async function configureSession() {
  const appSession = getAppSession();
  await appSession.clearCache();
  await appSession.clearStorageData({
    storages: ["cookies", "localstorage", "indexdb", "cachestorage", "websql", "serviceworkers", "shadercache"],
  });
  appSession.setPermissionCheckHandler(() => false);
  appSession.setPermissionRequestHandler((_webContents, _permission, callback) => callback(false));

  appSession.webRequest.onBeforeSendHeaders((details, callback) => {
    if (!localApiToken || !DEV_RENDERER_URL) {
      callback({ requestHeaders: details.requestHeaders });
      return;
    }

    try {
      const targetUrl = new URL(details.url);
      if (targetUrl.origin === DEV_RENDERER_ORIGIN && targetUrl.pathname.startsWith("/api")) {
        callback({
          requestHeaders: {
            ...details.requestHeaders,
            Authorization: `Bearer ${localApiToken}`,
          },
        });
        return;
      }
    } catch {
      // Ignore invalid URLs and keep the request unchanged.
    }
    callback({ requestHeaders: details.requestHeaders });
  });

  if (typeof appSession.setDevicePermissionHandler === "function") {
    appSession.setDevicePermissionHandler(() => false);
  }
}

function configureIpcHandlers() {
  ipcMain.handle("jira-token:store", (_event, token) => storeJiraTokenFromRenderer(token));
  ipcMain.handle("desktop-save:pdf", (_event, payload) => savePdfFromRenderer(payload));
  ipcMain.handle("desktop-open:external", (_event, targetUrl) => openExternalUrl(targetUrl));
  ipcMain.handle("desktop-storage:info", () => getDesktopStorageInfo());
  ipcMain.handle("desktop-storage:backup", () =>
    desktopStorageOperations.run("backup", () => createDesktopBackup()),
  );
  ipcMain.handle("desktop-storage:restore", () =>
    desktopStorageOperations.run("restore", () => restoreDesktopBackup()),
  );
  ipcMain.handle("desktop-storage:clear-data", () =>
    desktopStorageOperations.run("clear-data", () => clearDesktopData()),
  );
  ipcMain.handle("desktop-storage:factory-reset", () =>
    desktopStorageOperations.run("factory-reset", () => factoryResetDesktopData()),
  );
  ipcMain.handle("desktop-storage:reveal", () => revealDesktopDataFolder());
}

function showBackendErrorScreen(message, detail) {
  if (mainWindow && !mainWindow.isDestroyed()) {
    void mainWindow.loadURL(backendErrorScreenUrl(message, detail));
    if (mainWindow.isMinimized()) {
      mainWindow.restore();
    }
    mainWindow.show();
    mainWindow.focus();
    return;
  }
  dialog.showErrorBox("LighthousePM backend error", `${message}\n\n${detail ?? ""}`);
}

function getValidatedUpdateFeedUrl() {
  if (!UPDATE_FEED_URL || !app.isPackaged) {
    return null;
  }

  try {
    const updateFeedUrl = new URL(UPDATE_FEED_URL);
    if (updateFeedUrl.protocol === "https:") {
      return updateFeedUrl.toString();
    }
  } catch {
    // Invalid update feed URLs are ignored.
  }
  return null;
}

function configureOptionalUpdates() {
  const updateFeedUrl = getValidatedUpdateFeedUrl();
  if (!updateFeedUrl) {
    return;
  }

  autoUpdater.setFeedURL({ url: updateFeedUrl });
  autoUpdater.on("error", () => {
    // Update checks are optional and should never block local app usage.
  });
  autoUpdater.on("update-downloaded", (_event, _releaseNotes, releaseName) => {
    void dialog
      .showMessageBox(mainWindow ?? undefined, {
        type: "info",
        title: "LighthousePM Update Ready",
        message: "A LighthousePM update is ready to install.",
        detail: releaseName ? `Version: ${releaseName}` : "Restart the app to install the downloaded update.",
        buttons: ["Restart and install", "Later"],
        defaultId: 0,
        cancelId: 1,
      })
      .then((result) => {
        if (result.response === 0) {
          isQuitting = true;
          autoUpdater.quitAndInstall();
        }
      });
  });
  setTimeout(() => autoUpdater.checkForUpdates(), 10000);
}

function createMainWindow(initialUrl = startupScreenUrl()) {
  mainWindow = new BrowserWindow({
    width: 1440,
    height: 960,
    minWidth: 1100,
    minHeight: 700,
    show: false,
    autoHideMenuBar: true,
    backgroundColor: "#f4f7fb",
    title: "LighthousePM",
    webPreferences: {
      preload: path.join(__dirname, "preload.cjs"),
      partition: APP_SESSION_PARTITION,
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
      webSecurity: true,
      allowRunningInsecureContent: false,
      spellcheck: false,
    },
  });

  mainWindow.once("ready-to-show", () => {
    mainWindow?.show();
  });

  mainWindow.webContents.on("will-navigate", (event, targetUrl) => {
    if (isAllowedAppNavigation(targetUrl)) {
      return;
    }
    event.preventDefault();
    openExternalUrl(targetUrl);
  });

  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    openExternalUrl(url);
    return { action: "deny" };
  });

  mainWindow.webContents.on("will-attach-webview", (event) => {
    event.preventDefault();
  });

  mainWindow.on("closed", () => {
    mainWindow = null;
  });

  void mainWindow.loadURL(initialUrl);
}

async function startApplication() {
  await configureSession();
  configureIpcHandlers();
  createMainWindow();
  try {
    const recoveryResult = await recoverDesktopStorageAtStartup();
    if (!recoveryResult.backendStarted) {
      await startBackend();
    }
    rendererOrigin = getDevRendererOrigin() ?? (await startRendererServer());
    await mainWindow?.loadURL(rendererOrigin);
    configureOptionalUpdates();
  } catch (error) {
    const detail = error instanceof Error ? error.message : "Unknown startup error";
    showBackendErrorScreen("LighthousePM could not start the local backend.", detail);
  }
}

if (hasSingleInstanceLock) {
  app.on("second-instance", () => {
    if (mainWindow) {
      if (mainWindow.isMinimized()) {
        mainWindow.restore();
      }
      mainWindow.focus();
    }
  });

  app.whenReady().then(startApplication).catch((error) => {
    const detail = error instanceof Error ? error.message : "Unknown startup error";
    dialog.showErrorBox("LighthousePM could not start", detail);
    app.quit();
  });

  app.on("activate", () => {
    if (BrowserWindow.getAllWindows().length === 0 && rendererOrigin) {
      createMainWindow();
    }
  });

  app.on("window-all-closed", () => {
    if (process.platform !== "darwin") {
      app.quit();
    }
  });

  app.on("before-quit", () => {
    isQuitting = true;
    rendererServer?.close();
    rendererServer = null;
    void stopBackend().catch(() => {});
  });
}
