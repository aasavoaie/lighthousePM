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

This is not yet an installer. Installer generation belongs to a later desktop
milestone.

The packaged directory includes the Python runtime and all backend
dependencies. Running `LighthousePM.exe` starts and stops the backend
automatically.

## Local Data

The desktop application stores its mutable files under the current Windows
user's application-data directory:

```text
%APPDATA%\LighthousePM\data\lighthouse.db
%APPDATA%\LighthousePM\logs\backend.log
```

Nothing is sent to an external LighthousePM service. Jira requests still go
directly from the local backend to the configured Jira Cloud instance.

## Jira Configuration

Jira credentials are deliberately not embedded in the packaged application.
Create a `backend.env` file in either location:

```text
%APPDATA%\LighthousePM\backend.env
<directory containing LighthousePM.exe>\backend.env
```

Use the Jira-related settings from `backend/.env.example`. During repository
development, Electron reads `backend/.env` automatically. The desktop runtime
always supplies its own SQLite database path, loopback port, and CORS settings.

## Security Boundary

- Renderer sandboxing and context isolation are enabled.
- Node.js is disabled in the renderer.
- Browser permissions, webviews, and unexpected navigation are blocked.
- Only HTTPS links may be opened in the system browser.
- The preload exposes only a read-only desktop runtime marker.
- Packaged frontend and API traffic stay on loopback interfaces.
- Jira credentials remain outside the packaged executable.
