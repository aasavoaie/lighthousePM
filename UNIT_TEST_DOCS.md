# UNIT TEST DOCS

This document summarizes the backend test suite by category and test module.

## Scope

- Test root: `backend/tests`
- Current total tests: `112`
- Main command:

```bash
cd backend
python -m pytest tests/ -v --tb=short
```

## Categories

### 1) API Contract Tests

Focus: endpoint behavior, response contracts, error handling, and pagination/filter semantics.

- `test_health.py` (1)
  - Verifies `/health` response contract and environment/service fields.

- `test_releases_api.py` (5)
  - Validates release list/get endpoints, issue listing under release, pagination, and 404 behavior.

- `test_issues_api.py` (2)
  - Validates issue lookup endpoint success and not-found behavior.

- `test_metrics_api.py` (11)
  - Validates metrics/charts empty state and computed state responses.
  - Validates recompute endpoints (`/releases/{id}/recompute` and `/releases/recompute-all`).
  - Validates chart query params (`limit`, `from`, `to`) and invalid-range handling.

- `test_signals_api.py` (4)
  - Validates signal endpoint empty/computed states and threshold/reason details behavior.

- `test_sync_api.py` (2)
  - Validates sync endpoint response shape and service error mapping to HTTP 400.

- `test_admin_api.py` (2)
  - Validates `/admin/status` empty and populated operational-status responses.

### 2) Service Logic Unit Tests

Focus: deterministic metric/signal/sync/Jira logic independent from HTTP routing.

- `test_analytics_service.py` (20)
  - Metric computation rules across all metric families.
  - Boundary and case-insensitive handling.
  - Churn/reopen/cycle-time assumptions and edge cases.

- `test_signal_service.py` (28)
  - RED/YELLOW/GREEN rule evaluation and threshold boundaries.
  - Multi-trigger reasoning and edge-case validation.

- `test_jira_service.py` (14)
  - Jira API wrapper behavior with mocked transport.
  - Parsing/normalization behavior for issues/changelog/versions.
  - Error mapping (auth, rate-limit, network, malformed payloads).

- `test_sync_service.py` (4)
  - End-to-end sync service orchestration with fake Jira data.
  - Persistence counts, idempotency, recompute side effects, and failure sanitization.

### 3) Integration & Pipeline Tests

Focus: realistic end-to-end deterministic flow across ingestion/model/service boundaries.

- `test_pipeline_integration.py` (10)
  - Validates full pipeline scenarios: data -> metrics snapshots -> release signals.
  - Confirms signal outcomes for representative release-risk conditions.

### 4) Configuration, DB, and Utility Tests

Focus: startup safety, model registration, and shared utility behavior.

- `test_config.py` (4)
  - Settings defaults, cache behavior, and startup validation rules.

- `test_db.py` (2)
  - MVP table registration and DB initialization behavior.

- `test_error_sanitizer.py` (2)
  - Sensitive-value redaction and message truncation behavior.

- `test_seed.py` (1)
  - Seed script smoke test and idempotency checks for local/demo data.

## Test Inventory Summary

| Category | Modules | Test Count |
|---|---:|---:|
| API Contract | 7 | 27 |
| Service Logic | 4 | 66 |
| Integration & Pipeline | 1 | 10 |
| Config/DB/Utility | 4 | 9 |
| **Total** | **16** | **112** |

## Notes

- Most API tests use FastAPI `TestClient` with in-memory SQLite (`StaticPool`) for deterministic isolation.
- Service tests prioritize deterministic, threshold-boundary logic over framework-level behavior.
- Integration tests provide confidence that metric and signal rules remain coherent across the full pipeline.
