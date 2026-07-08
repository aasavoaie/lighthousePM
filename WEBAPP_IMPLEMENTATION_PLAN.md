# LighthousePM Webapp Implementation Plan

This plan turns the current FastAPI backend and React dashboard into a deployable
webapp while preserving the repository rules in `AGENTS.md`:

- deterministic metrics and signals
- one backend service
- PostgreSQL storage
- thin API routes
- service-owned business logic
- structured, explainable JSON outputs

## Current Baseline

- Backend: FastAPI, SQLAlchemy, PostgreSQL-ready, deterministic service layer.
- Frontend: React + TypeScript + Vite, already reads the backend through
  `VITE_API_BASE_URL`.
- Desktop: Electron shell remains optional and should not own web behavior.
- Runtime probes:
  - `GET /health` is liveness: process is up.
  - `GET /ready` is readiness: process can reach storage.

## Phase 1: Web Runtime Foundation

- Keep `/health` lightweight for platform liveness probes.
- Use `/ready` for load balancer and deployment readiness checks.
- Configure `CORS_ORIGINS` per deployed frontend origin.
- Configure `VITE_API_BASE_URL` per deployed backend URL or reverse-proxy path.
- Keep `DATABASE_URL` pointed at PostgreSQL for shared web deployments.
- Set `LIGHTHOUSE_API_TOKEN` for protected API access until full web auth lands.

## Phase 2: Authentication And Admin Safety

- Keep read and write API contracts stable.
- Require authentication for configuration, sync, recompute, reports, and admin
  endpoints in web deployments.
- Keep health and readiness endpoints unauthenticated for platform probes.
- Avoid putting business authorization logic in API routes; use focused security
  helpers or dependencies.

## Phase 3: Deployment Shape

- Build frontend with `npm run build` from `frontend/`.
- Run backend with Uvicorn from `backend/`.
- Serve the frontend as static assets and route API calls to FastAPI.
- Start with one deployment unit or Docker Compose; split frontend and backend
  hosting only if deployment constraints require it.
- Run Alembic migrations before serving traffic.

## Phase 4: Operational Flow

- Jira sync remains explicit and deterministic.
- Scheduled sync is opt-in with `JIRA_SYNC_INTERVAL_SECONDS`.
- Sync, metrics recompute, and signal recompute must continue to emit sanitized
  operational status.
- Dashboard freshness should rely on existing snapshot timestamps and
  operational status fields.

## Phase 5: Acceptance Checklist

- Fresh database migrates to head.
- `GET /health` returns `200`.
- `GET /ready` returns `200` only when storage is reachable.
- Frontend build succeeds with production `VITE_API_BASE_URL`.
- Backend tests pass.
- Frontend assertion tests pass.
- Jira configuration can be saved and tested.
- Jira sync ingests releases, sprints, issues, and changelog data.
- Metrics and signals recompute with explicit thresholds and reasons.
- Dashboard renders releases, sprints, charts, recommendations, and reports from
  the deployed backend.
