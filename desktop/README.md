# LighthousePM Desktop Shell

This package runs the React frontend and a packaged FastAPI backend as one
desktop application. The end user does not need Python, Node.js, PostgreSQL,
or a separately started server.

## Setup

From `desktop/`:

```bash
npm install
```

## Development

```bash
npm run dev
```

This packages the backend, starts Vite on `127.0.0.1:5173`, launches the local
backend on `127.0.0.1:8000`, and opens Electron with frontend hot reload.

## Run The Compiled Frontend

```bash
npm start
```

This packages the backend, builds the React frontend, starts both from local
application resources, and opens Electron.

## Create A Windows App Directory

```bash
npm run package
```

The unpacked Windows application is generated under:

```text
desktop/out/LighthousePM-win32-x64/
```

The packaged directory includes the Python runtime and all backend
dependencies. Running `LighthousePM.exe` starts and stops the backend
automatically.

## Create Windows Distribution Artifacts

```bash
npm run make
```

This builds the backend, builds the frontend, packages Electron, and creates:

```text
desktop/out/make/squirrel.windows/x64/LighthousePM-Setup.exe
desktop/out/make/zip/win32/x64/
```

Use the setup EXE for a normal Windows installation. Use the zip artifact when
the app should be distributed as an unpack-and-run folder.

## Local Data

The desktop application stores its mutable files under the current Windows
user's application-data directory:

```text
%APPDATA%\LighthousePM\data\lighthouse.db
%APPDATA%\LighthousePM\logs\backend.log
%APPDATA%\LighthousePM\backend.env
%APPDATA%\LighthousePM\secrets\jira-token.bin
```

Nothing is sent to an external LighthousePM service. Jira requests still go
directly from the local backend to the configured Jira Cloud instance.

### What Is Stored

- `lighthouse.db`: normalized Jira project, release, sprint, issue, changelog,
  metric, signal, and operational-status data.
- `backend.env`: non-secret Jira connection settings such as base URL, email,
  project key, field mappings, sync limits, and sync interval.
- `jira-token.bin`: Jira API token encrypted with Electron `safeStorage`.
- `backend.log`: local backend startup and operational logs.

### What Is Not Stored

- The Jira API token is not written to `backend.env` or SQLite.
- The per-launch local API bearer token is not written to disk.
- Raw Jira issue descriptions, labels, components, reporters, and changelog
  authors are not requested or normalized by the sync path.
- Chromium cookies, local storage, IndexedDB, cache storage, service workers,
  web SQL, shader cache, and HTTP cache are cleared on app startup and the app
  uses a non-persistent Electron session partition.

### Retention And Cleanup

- `backend.log` rotates when it exceeds 1 MB.
- Up to 5 rotated backend logs are kept.
- Rotated backend logs older than 14 days are pruned on startup.
- Synced Jira data is retained locally until the user chooses Clear Data,
  Restore, or Factory Reset from Settings.
- Clear Data removes the local SQLite database and keeps settings plus the
  encrypted token.
- Factory Reset removes local database files, settings, logs, and encrypted
  token, then restarts the backend.

## Jira Configuration

Jira credentials are deliberately not embedded in the packaged application.
Users should configure Jira from Settings inside the app. Non-secret settings
are written to:

```text
%APPDATA%\LighthousePM\backend.env
```

The Jira token is encrypted with Electron `safeStorage` and written to:

```text
%APPDATA%\LighthousePM\secrets\jira-token.bin
```

For migration only, a sidecar `backend.env` next to `LighthousePM.exe` may be
read. If it contains `JIRA_API_TOKEN`, Electron encrypts that token into
`safeStorage` and removes the plaintext token from the env file. During
repository development, Electron reads `backend/.env` automatically. The
desktop runtime always supplies its own SQLite database path, loopback port,
per-launch API token, and CORS settings.

## Security Boundary

- Renderer sandboxing and context isolation are enabled.
- Node.js is disabled in the renderer.
- Browser permissions, webviews, and unexpected navigation are blocked.
- Only HTTPS links may be opened in the system browser.
- The preload exposes only narrow desktop operations for encrypted token
  storage, local storage status, backup, restore, data clearing, factory reset,
  and opening the data folder.
- Packaged frontend and API traffic stay on loopback interfaces.
- Jira credentials remain outside the packaged executable.
- The backend rejects protected API calls unless Electron adds the per-launch
  bearer token.
- Backend logs redact obvious token, password, authorization, and secret values.
