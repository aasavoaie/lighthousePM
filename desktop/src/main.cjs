const { app, BrowserWindow, dialog, session, shell } = require("electron");
const { spawn } = require("node:child_process");
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

  const userDataDirectory = app.getPath("userData");
  const dataDirectory = path.join(userDataDirectory, "data");
  const logsDirectory = path.join(userDataDirectory, "logs");
  const databasePath = path.join(dataDirectory, "lighthouse.db");
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

  const childEnvironment = { ...process.env };
  delete childEnvironment.ELECTRON_RUN_AS_NODE;
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
  const headers = { ...request.headers, host: new URL(backendOrigin).host };
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

  request.pipe(proxyRequest);
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

  if (typeof appSession.setDevicePermissionHandler === "function") {
    appSession.setDevicePermissionHandler(() => false);
  }
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
