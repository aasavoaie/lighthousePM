const { app, BrowserWindow, dialog, ipcMain, safeStorage, session, shell } = require("electron");
const { spawn } = require("node:child_process");
const crypto = require("node:crypto");
const fs = require("node:fs");
const http = require("node:http");
const net = require("node:net");
const path = require("node:path");

const LOOPBACK_HOST = "127.0.0.1";
const DEV_RENDERER_ORIGIN = "http://127.0.0.1:5173";
const DEV_BACKEND_PORT = 8000;
const DEV_RENDERER_URL = process.env.ELECTRON_RENDERER_URL;
const BACKEND_STARTUP_TIMEOUT_MS = 30000;
const BACKEND_HEALTH_RETRY_MS = 200;
const BACKUP_VERSION = 1;

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

app.enableSandbox();

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

function getBackendEnvFile() {
  if (app.isPackaged) {
    const userConfigPath = path.join(app.getPath("userData"), "backend.env");
    const sidecarConfigPath = path.join(path.dirname(app.getPath("exe")), "backend.env");
    return fs.existsSync(sidecarConfigPath) ? sidecarConfigPath : userConfigPath;
  }
  return path.resolve(__dirname, "../../backend/.env");
}

function getDesktopDataPaths() {
  const userDataDirectory = app.getPath("userData");
  const dataDirectory = path.join(userDataDirectory, "data");
  const logsDirectory = path.join(userDataDirectory, "logs");
  const secretsDirectory = path.join(userDataDirectory, "secrets");
  const databasePath = path.join(dataDirectory, "lighthouse.db");
  return {
    userDataDirectory,
    dataDirectory,
    logsDirectory,
    secretsDirectory,
    databasePath,
    configPath: getBackendEnvFile(),
    tokenPath: getEncryptedJiraTokenPath(),
  };
}

function getEncryptedJiraTokenPath() {
  return path.join(app.getPath("userData"), "secrets", "jira-token.bin");
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

  const logDescriptor = fs.openSync(logPath, "w");
  try {
    backendProcess = spawn(executablePath, args, {
      env: childEnvironment,
      stdio: ["ignore", logDescriptor, logDescriptor],
      windowsHide: true,
    });
  } finally {
    fs.closeSync(logDescriptor);
  }

  backendProcess.once("error", (error) => {
    if (!isQuitting) {
      dialog.showErrorBox("LighthousePM backend error", `${error.message}\n\nLog: ${logPath}`);
      app.quit();
    }
  });
  backendProcess.once("exit", (code) => {
    backendProcess = null;
    if (!isQuitting) {
      dialog.showErrorBox(
        "LighthousePM backend stopped",
        `The local backend exited with code ${code ?? "unknown"}.\n\nLog: ${logPath}`,
      );
      app.quit();
    }
  });

  await waitForBackend(backendOrigin, logPath);
}

function stopBackend() {
  if (backendProcess && backendProcess.exitCode === null) {
    backendProcess.kill();
  }
  backendProcess = null;
}

function sleep(milliseconds) {
  return new Promise((resolve) => setTimeout(resolve, milliseconds));
}

async function restartBackend() {
  stopBackend();
  await sleep(400);
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

function deleteDatabaseFiles(databasePath) {
  deleteIfExists(databasePath);
  deleteIfExists(`${databasePath}-shm`);
  deleteIfExists(`${databasePath}-wal`);
}

function copyIfExists(sourcePath, targetPath) {
  if (!fs.existsSync(sourcePath)) {
    return false;
  }
  fs.mkdirSync(path.dirname(targetPath), { recursive: true });
  fs.copyFileSync(sourcePath, targetPath);
  return true;
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

  const copied = {
    database: copyIfExists(paths.databasePath, path.join(backupDirectory, "data", "lighthouse.db")),
    databaseWal: copyIfExists(`${paths.databasePath}-wal`, path.join(backupDirectory, "data", "lighthouse.db-wal")),
    databaseShm: copyIfExists(`${paths.databasePath}-shm`, path.join(backupDirectory, "data", "lighthouse.db-shm")),
    config: copyIfExists(paths.configPath, path.join(backupDirectory, "backend.env")),
    encryptedToken: copyIfExists(paths.tokenPath, path.join(backupDirectory, "secrets", "jira-token.bin")),
  };
  const manifest = {
    app: "LighthousePM",
    version: BACKUP_VERSION,
    createdAt: new Date().toISOString(),
    copied,
  };
  fs.writeFileSync(path.join(backupDirectory, "manifest.json"), JSON.stringify(manifest, null, 2), "utf8");
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
  const paths = getDesktopDataPaths();
  stopBackend();
  await sleep(400);
  copyIfExists(path.join(backupDirectory, "data", "lighthouse.db"), paths.databasePath);
  copyIfExists(path.join(backupDirectory, "data", "lighthouse.db-wal"), `${paths.databasePath}-wal`);
  copyIfExists(path.join(backupDirectory, "data", "lighthouse.db-shm"), `${paths.databasePath}-shm`);
  copyIfExists(path.join(backupDirectory, "backend.env"), paths.configPath);
  copyIfExists(path.join(backupDirectory, "secrets", "jira-token.bin"), paths.tokenPath);
  await startBackend();
  return { ok: true, message: "Backup restored.", path: backupDirectory };
}

async function clearDesktopData() {
  const paths = getDesktopDataPaths();
  stopBackend();
  await sleep(400);
  deleteDatabaseFiles(paths.databasePath);
  await startBackend();
  return { ok: true, message: "Local synced data cleared." };
}

async function factoryResetDesktopData() {
  const paths = getDesktopDataPaths();
  stopBackend();
  await sleep(400);
  deleteDatabaseFiles(paths.databasePath);
  deleteIfExists(paths.configPath);
  deleteIfExists(paths.tokenPath);
  deleteIfExists(paths.logsDirectory);
  await startBackend();
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
    }
  } catch {
    // Invalid external URLs are ignored.
  }
}

function configureSession() {
  const appSession = session.defaultSession;
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
  ipcMain.handle("desktop-storage:info", () => getDesktopStorageInfo());
  ipcMain.handle("desktop-storage:backup", () => createDesktopBackup());
  ipcMain.handle("desktop-storage:restore", () => restoreDesktopBackup());
  ipcMain.handle("desktop-storage:clear-data", () => clearDesktopData());
  ipcMain.handle("desktop-storage:factory-reset", () => factoryResetDesktopData());
  ipcMain.handle("desktop-storage:reveal", () => revealDesktopDataFolder());
}

function createMainWindow() {
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

  void mainWindow.loadURL(rendererOrigin);
}

async function startApplication() {
  configureSession();
  configureIpcHandlers();
  await startBackend();
  rendererOrigin = getDevRendererOrigin() ?? (await startRendererServer());
  createMainWindow();
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
    stopBackend();
  });
}
