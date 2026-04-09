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

Example `GET /releases/REL-1/metrics` (snapshot exists):

```json
{
  "release_id": "REL-1",
  "snapshot_at": "2026-04-09T12:00:00Z",
  "metrics": {
    "open_blockers": 1,
    "open_high_severity_bugs": 2,
    "scope_completed_pct": 55.56,
    "scope_churn_7d_pct": 12.5,
    "median_cycle_time_days": 4.0,
    "reopen_rate_pct": 8.33
  }
}
```

Example `GET /releases/REL-1/metrics` (empty state, release exists):

```json
{
  "release_id": "REL-1",
  "snapshot_at": null,
  "metrics": {
    "open_blockers": null,
    "open_high_severity_bugs": null,
    "scope_completed_pct": null,
    "scope_churn_7d_pct": null,
    "median_cycle_time_days": null,
    "reopen_rate_pct": null
  }
}
```

Example `GET /releases/REL-1/charts?limit=2`:

```json
{
  "release_id": "REL-1",
  "series": {
    "open_blockers": [
      {"snapshot_at": "2026-04-09T11:00:00Z", "value": 2},
      {"snapshot_at": "2026-04-09T12:00:00Z", "value": 1}
    ],
    "open_high_severity_bugs": [
      {"snapshot_at": "2026-04-09T11:00:00Z", "value": 2},
      {"snapshot_at": "2026-04-09T12:00:00Z", "value": 2}
    ],
    "scope_completed_pct": [
      {"snapshot_at": "2026-04-09T11:00:00Z", "value": 50.0},
      {"snapshot_at": "2026-04-09T12:00:00Z", "value": 55.56}
    ],
    "scope_churn_7d_pct": [
      {"snapshot_at": "2026-04-09T11:00:00Z", "value": 15.0},
      {"snapshot_at": "2026-04-09T12:00:00Z", "value": 12.5}
    ],
    "median_cycle_time_days": [
      {"snapshot_at": "2026-04-09T11:00:00Z", "value": 5.0},
      {"snapshot_at": "2026-04-09T12:00:00Z", "value": 4.0}
    ],
    "reopen_rate_pct": [
      {"snapshot_at": "2026-04-09T11:00:00Z", "value": 10.0},
      {"snapshot_at": "2026-04-09T12:00:00Z", "value": 8.33}
    ]
  }
}
```

Example `POST /releases/REL-1/recompute`:

```json
{
  "release_id": "REL-1",
  "snapshot_at": "2026-04-09T12:00:00Z",
  "status": "ok"
}
```

### Signals API Notes (MVP)

- `GET /releases/{id}/signal` returns the latest computed release signal.
- If a release exists but signal was not computed yet, returns `200` with:
  - `signal: null`
  - `reasons: []`
  - `updated_at: null`
- Signal rules are deterministic and threshold-based:
  - **RED** if any of:
    - `open_blockers > 0`
    - `open_high_severity_bugs > 1`
    - `scope_churn_7d_pct > 20%`
    - `reopen_rate_pct > 15%`
  - **YELLOW** if not RED and any of:
    - `open_high_severity_bugs > 0`
    - `scope_churn_7d_pct > 10%`
    - `reopen_rate_pct > 10%`
    - `median_cycle_time_days > 7`
  - **GREEN** otherwise.
- Percent metrics in DB are stored as `0-100` and normalized to `0-1` only for
  threshold comparisons.
- MVP retention policy: signal is stored as latest-only per release (updated in place).

Example `GET /releases/REL-1/signal` (signal exists):

```json
{
  "release_id": "REL-1",
  "signal": "YELLOW",
  "reasons": [
    "High-severity bugs present: 1 > 0",
    "Scope churn: 12.5% > 10.0%"
  ],
  "updated_at": "2026-04-09T12:00:00Z"
}
```

Example `GET /releases/REL-1/signal` (empty state, release exists):

```json
{
  "release_id": "REL-1",
  "signal": null,
  "reasons": [],
  "updated_at": null
}
```

### Modifying Signal Rules and Thresholds

Signal rules are **entirely deterministic and easy to modify**. To add a new rule or change thresholds:

#### 1. Define or update the threshold constant
In `app/utils/constants.py`:
```python
MY_NEW_METRIC_RED_THRESHOLD = 0.50  # Example: 50% of something
MY_NEW_METRIC_YELLOW_THRESHOLD = 0.25
```

#### 2. Update the `_evaluate_signal()` method
In `app/services/signal_service.py`, add a new condition in the RED or YELLOW section:
```python
# RED condition example:
if my_new_metric > MY_NEW_METRIC_RED_THRESHOLD:
    red_reasons.append(f"My metric: {my_new_metric:.1f} > {MY_NEW_METRIC_RED_THRESHOLD}")

# Or YELLOW condition:
if my_new_metric > MY_NEW_METRIC_YELLOW_THRESHOLD:
    yellow_reasons.append(f"My metric: {my_new_metric:.1f} > {MY_NEW_METRIC_YELLOW_THRESHOLD}")
```

**Important:** Include an inline comment above the condition explaining:
- **Why** this threshold exists (e.g., "indicates quality risk")
- **What value range** puts it in RED vs YELLOW
- **How it impacts** release decisions

#### 3. Add unit test cases
In `app/tests/test_signal_service.py`, add test cases for:
- Metric exactly at the threshold (boundary test)
- Metric above the threshold (trigger test)
- Metric interacting with other YELLOW/RED conditions
- Edge cases (null values, zero, very high values)

Example test:
```python
def test_red_my_new_metric_exceeds_threshold(self) -> None:
    signal, reasons = SignalService._evaluate_signal(
        ...,
        my_new_metric=0.51,
        ...
    )
    assert signal == "RED"
    assert any("my_metric" in r.lower() for r in reasons)
```

#### 4. Update this README
Document the new threshold and its intent in the "Release Signals" section above.

#### 5. Run tests
```bash
pytest backend/tests/test_signal_service.py -v
pytest backend/tests/test_signals_api.py -v
```

Ensure all tests pass, including boundary values and multiple simultaneous conditions.

**Rule of thumb:** Every threshold should have a comment explaining *why*, and every rule should have at least 2 test cases (boundary and trigger).

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
- Implemented services for Jira sync, metrics recompute, and release signal computation
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

This backend currently includes a working MVP path for:

- Jira sync ingestion (`POST /sync/jira`)
- Deterministic metrics snapshots (`metric_snapshots`)
- Deterministic release signals (`release_signals`)
- Release-level metrics/charts/signal read APIs

Known remaining gaps for full vision:

- Additional quality/flow metrics (for example, aging work and bug trend)
- Expanded signal tuning per team/project conventions