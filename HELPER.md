# API Helper

This file is a quick reference for every HTTP endpoint currently exposed by the backend.

The descriptions here follow the current implementation in `backend/app/api` and align with the repository rules in `README.md` and `AGENTS.md`:
- deterministic outputs only
- structured JSON responses
- thin API routes that delegate business logic to services

There is no global `/api` prefix at the moment. Routes are mounted exactly as listed below.

## Health

### `GET /health`
Returns a lightweight health response for the service.

What it does:
- confirms the API process is up
- returns the configured service name
- returns the configured environment name

Typical use:
- uptime checks
- deployment smoke tests
- environment verification

## Releases

### `GET /releases`
Returns a paginated list of releases known to the system.

What it does:
- lists release records from storage
- supports pagination with `skip` and `limit`

Query parameters:
- `skip`: pagination offset, default `0`
- `limit`: page size, default `50`, max `100`

### `GET /releases/{release_id}`
Returns one release by its release identifier.

What it does:
- looks up a release by `release_id`
- returns `404` if the release does not exist

Typical use:
- release detail pages
- validation that a release exists before requesting metrics or signal data

### `GET /releases/{release_id}/issues`
Returns the issues currently associated with a given release.

What it does:
- validates the release exists
- returns a paginated list of issues linked to that release
- includes issue fields used elsewhere in analytics, such as status, priority, assignee, and blocker flag

Query parameters:
- `skip`: pagination offset, default `0`
- `limit`: page size, default `50`, max `100`

Typical use:
- inspect all tickets in a release
- explain why a release signal was triggered
- feed release-scoped issue views in a dashboard

## Metrics

### `GET /releases/{release_id}/metrics`
Returns the latest computed metric snapshot for a release.

What it does:
- validates the release exists
- fetches the most recent metric snapshot for that release
- returns the current metric values and supporting metadata

Important behavior:
- if the release exists but no metrics have been computed yet, this still returns `200`
- in that empty state, `snapshot_at` is `null`, metric values are `null`, and `is_computed` is `false`
- when a snapshot exists, the response includes `metric_names`, `metric_thresholds`, and `snapshot_age_hours`

Typical use:
- current release health summary
- top-level dashboard cards
- determining whether metrics are fresh enough to trust

### `GET /releases/{release_id}/charts`
Returns time-series metric data for a release.

What it does:
- validates the release exists
- returns multiple metric series built from stored snapshots
- each series contains `snapshot_at` and `value` points only

Query parameters:
- `limit`: max snapshots returned, default `500`, max `5000`
- `from`: optional inclusive lower timestamp bound
- `to`: optional inclusive upper timestamp bound

Important behavior:
- returns `400` if `from > to`
- returns frontend-agnostic chart data rather than chart-library-specific payloads
- includes `metric_names` and `point_count`

Typical use:
- trend charts
- release burn and risk trend visualization
- comparing signal drivers over time

### `POST /releases/{release_id}/recompute`
Forces metric recomputation for a release and immediately refreshes its release signal.

What it does:
- recomputes release metrics from the current issue and history data
- writes a new metric snapshot
- recomputes the release signal based on the latest snapshot
- commits both changes in one request

Important behavior:
- returns `404` if the release does not exist or if metrics cannot be computed for it
- this is the manual path for forcing a fresh snapshot without waiting for scheduled sync

Typical use:
- operator-triggered refresh
- testing data changes quickly
- forcing fresh analytics after sync or seed activity

## Signals

### `GET /releases/{release_id}/signal`
Returns the latest computed release risk signal for a release.

What it does:
- validates the release exists
- reads the current stored signal row for the release
- returns the signal level, human-readable reasons, structured reason details, and explicit thresholds

Important behavior:
- if the release exists but signal has not been computed yet, this still returns `200`
- in that empty state, `signal` is `null`, `reasons` is empty, `reason_details` is empty, and `updated_at` is `null`
- thresholds are always returned so clients do not need to hardcode rule boundaries

Typical use:
- release readiness indicators
- traffic-light widgets in dashboards
- programmatic inspection of why a release is `RED` or `YELLOW`

## Issues

### `GET /issues/{jira_key}`
Returns a single issue by Jira key.

What it does:
- looks up an issue by `jira_key`
- returns `404` if the issue does not exist

Typical use:
- drill-down from release issue lists
- issue detail views
- validating a specific ingested ticket exists in local storage

## Admin

### `GET /admin/status`
Returns the latest persisted operational markers for sync and recomputation activity.

What it does:
- returns last successful sync timestamp
- returns last failed sync timestamp and sanitized failure summary
- returns last metrics recompute timestamp
- returns last signal recompute timestamp

Typical use:
- operational debugging in local/internal deployments
- quickly checking if sync or recomputation recently failed
- confirming recompute activity without scanning logs

## Sync

### `POST /sync/jira`
Triggers Jira ingestion and downstream recomputation work.

What it does:
- runs the Jira sync service
- ingests or updates releases, issues, and related history
- performs the follow-on analytics work defined by the sync service

Important behavior:
- returns `400` when the sync service raises a controlled sync error
- intended as an operator/admin endpoint rather than an end-user dashboard call

Typical use:
- manual refresh from Jira
- operational sync trigger
- validating Jira credentials and upstream connectivity

## Notes and Current Limits

- There is currently no sprint-scoped endpoint such as `GET /sprints/{id}/issues`.
- Issues are currently grouped by release, not by sprint.
- The API is intentionally narrow and explicit: release listing, issue lookup, metrics, signals, and Jira sync.
- Signal and metric behavior is deterministic and threshold-based; route handlers do orchestration only and keep business logic in services.