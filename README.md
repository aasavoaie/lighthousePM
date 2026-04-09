# Jira Release Signals

A backend service that wraps Jira and produces **deterministic release analytics and risk signals**.

---

## 🎯 Problem

Jira tracks work but does not answer:

- Is this release safe?
- What changed recently?
- Where are the risks?
- Why are we slipping?

This project turns Jira data into **clear, explainable release signals**.

---

## 🧠 Approach

The system is built in layers:
Jira → Ingestion → Database → Metrics → Signals → API

### Key principle

> Deterministic analytics decide.

---

## 🚀 MVP Scope

### Included
- Jira ingestion (issues + changelog)
- PostgreSQL storage
- Deterministic metrics
- Rule-based release signals
- JSON API for dashboards

### Not included
- Multi-project scaling
- Microservices
- Advanced statistical modeling

---

## 📊 Core Metrics

### Release Health
- Open blockers
- Open high-severity bugs
- % of release scope completed
- Scope churn (last 7 days)

### Flow
- Median cycle time
- Aging work

### Quality
- Reopen rate
- Bug trend

---

## 🚦 Release Signals

Signals are deterministic and explainable.

### RED
- Open blockers > 0
- OR high-severity bugs above threshold
- OR scope churn > 20% (7d)
- OR reopen rate > 15%

### YELLOW
- Moderate risk conditions
- Elevated cycle time
- Medium scope churn (10–20%)

### GREEN
- No major risk indicators

Each signal includes **explicit reasons**.

---

## 🏗️ Architecture

Single-service backend:

- FastAPI (API layer)
- PostgreSQL (data store)
- Services layer:
  - `jira_service`
  - `sync_service`
  - `analytics_service`
  - `signal_service`

---

## 🔄 Data Flow

1. Fetch Jira issues + changelog
2. Store normalized data
3. Compute metrics
4. Compute release signal
5. Expose via API

---

## 🗄️ Data Model (MVP)

### issues
Core issue state (latest snapshot)

### issue_history
Field changes (especially status transitions)

### releases
Release/version metadata

### metric_snapshots
Time-series metric values

### release_signals
Final release health output

---

## 🔌 API (MVP)

### Health
- `GET /health`

### Releases
- `GET /releases`
- `GET /releases/{id}`

### Metrics
- `GET /releases/{id}/metrics`
- `GET /releases/{id}/charts`

### Signals
- `GET /releases/{id}/signal`

### Issues
- `GET /releases/{id}/issues`
- `GET /issues/{key}`

### Admin
- `POST /sync/jira`
- `POST /releases/{id}/recompute`

### Metrics API Notes (MVP)

- `GET /releases/{id}/metrics` returns the latest computed snapshot for a release.
- If a release exists but has no snapshots yet, metrics returns `200` with:
  - `snapshot_at: null`
  - all metric fields set to `null`
- `GET /releases/{id}/charts` returns frontend-agnostic series data:
  - one array per metric
  - each item has `snapshot_at` and `value`
  - no chart-library-specific payloads
- Optional query parameters for charts:
  - `limit` (default `500`) returns the latest N snapshots
  - `from` and `to` apply inclusive datetime bounds (`from <= snapshot_at <= to`)
  - when `from > to`, API returns `400`
- Unknown release IDs return `404`.

---

## ⚙️ Tech Stack

- Python + FastAPI
- PostgreSQL
- SQLAlchemy / SQLModel
- httpx (Jira API)
- APScheduler (MVP jobs)
- Docker (local setup)

---

## 🔁 Sync Strategy

MVP:
- Poll Jira every 15–30 minutes

Later:
- Replace with Jira webhooks

---

## 🧩 Project Structure
backend/
app/
api/
services/
models/
schemas/
db/
jobs/
utils/


---

## 🧪 Development Steps

1. Jira ingestion
2. Database schema
3. Metrics engine
4. Signal engine
5. API endpoints
6. Charts (frontend)

---

## 🎯 Success Criteria

- Signals match real team experience
- Metrics are trusted
- Output is explainable
- System is simple to run and extend

---

## 📌 Philosophy

> Build a system engineers trust — not one that guesses.

---

## 🧰 Local Development (Current Scaffold)

This repository now includes an initial backend scaffold in `backend/` with:

- FastAPI app entrypoint
- Environment-based config loading
- Thin health endpoint: `GET /health`
- Service/module placeholders for future Jira sync, metrics, and signals
- Docker Compose for backend + Postgres

### Run with Docker

From repository root:

```bash
docker compose up --build
```

Health check:

```bash
curl http://localhost:8000/health
```

### Run locally (without Docker)

From `backend/`:

```bash
python -m pip install -e .
python -m pip install -r requirements-dev.txt
uvicorn app.main:app --reload --port 8000
```

### Database Foundation (MVP)

The backend now includes a migration-ready PostgreSQL foundation with these tables:

- `issues`
- `issue_history`
- `releases`
- `metric_snapshots`
- `release_signals`

For local development, app startup runs a simple initialization path that calls
SQLAlchemy metadata create for missing tables.

Alembic is configured for migration-driven schema evolution.

From `backend/`:

```bash
alembic upgrade head
```

Create a new migration after model changes:

```bash
alembic revision -m "describe change"
```

### Current Scope Note

This is a scaffold-only MVP baseline.

Not implemented yet:

- Jira ingestion/sync behavior
- Metrics computation logic
- Release signal rule execution