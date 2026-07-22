# API Helper

This is the practical reference for the LighthousePM HTTP API. FastAPI's
OpenAPI document is authoritative for mechanical request and response schemas;
this file explains authentication, operational use, and important empty,
partial, historical, and error behavior.

There is no `/api` prefix. Routes are mounted exactly as listed below.

## Authentication and common behavior

`GET /health` is the only public endpoint. All other application endpoints,
including `/docs`, `/redoc`, and `/openapi.json`, require the configured bearer
token whenever API authentication is enabled:

```http
Authorization: Bearer <LIGHTHOUSE_API_TOKEN>
```

Authentication is always enabled in production, for non-loopback bindings,
and in desktop and Docker modes. Loopback `dev` or `test` local-browser mode
may run without authentication when no token is configured. Once a token is
configured, it protects that mode immediately.

LighthousePM classifies routes as public health, protected reads, or privileged
operations. The same operator token currently authorizes both protected
classes; there are no native user roles. Privileged operations include Jira
configuration, administration status, sync, and metric recomputation.

Common responses:

- `401` means bearer authentication failed. Jira authentication failure during
  sync can also produce `401` with a sanitized detail.
- `404` means the requested release, sprint, issue, or report entity is unknown.
- `422` means FastAPI rejected a path, query, or body value before the route ran.
- Controlled service failures use structured JSON with a `detail` field.
- Privileged responses and errors use `Cache-Control: no-store`.
- Existing releases or sprints without snapshots return structured `200`
  responses with unavailable values; they are not treated as unknown entities.

## Health and metadata

### `GET /health`

Returns `status`, service name, and environment. Use it for readiness, uptime,
and deployment smoke checks. It is the only endpoint that never requires the
API bearer token.

### `GET /metadata/metrics`

Returns the canonical release and sprint metric catalog in deterministic
display order.

The response includes:

- catalog and ruleset versions;
- stable metric keys, API fields, locations, labels, and descriptions;
- categories, units, formatting rules, and display order;
- thresholds and their meanings;
- availability dependencies, partial-value policy, evidence paths, and minimum
  coverage where applicable;
- historical, signal, confidence, chart, and report participation.

It contains no API tokens, Jira credentials, database configuration, or other
secrets. Clients should consume this endpoint instead of maintaining competing
metric labels or thresholds.

## Jira configuration and operations

### `GET /config/jira`

Returns effective nonsecret Jira configuration, the writable configuration
path, whether a Jira token is configured, and whether required settings are
complete. The token value is never returned.

### `PUT /config/jira`

Validates and atomically saves supplied Jira configuration fields. Omitted
fields keep their current values. Invalid page sizes, intervals,
classifications, or startup combinations return `400`.

Credential behavior is deployment-specific:

- non-Electron deployments reject `jira_api_token` persistence; configure
  `JIRA_API_TOKEN` or `JIRA_API_TOKEN_FILE` externally and restart the backend;
- nonsecret settings can be persisted to the configured writable file;
- Docker writes require a writable file mounted through
  `LIGHTHOUSE_CONFIG_FILE`;
- the Electron integration stores the Jira token through operating-system
  `safeStorage`, outside the nonsecret configuration file.

### `POST /config/jira/test`

Tests Jira authentication and access to the configured project. The optional
JSON body uses the same fields as `PUT /config/jira`, so an unsaved token or
other candidate values can be tested without persisting them.

The normal result is a structured `200` with `ok`, a message, optional account
identity, project key, and `project_accessible`. Configuration validation
errors can return `400`; Jira connection failures normally return `ok: false`
with a sanitized message.

### `GET /admin/status`

Returns the service and environment plus the latest persisted timestamps for:

- successful and failed Jira sync;
- sanitized sync failure summary;
- metric recomputation;
- signal recomputation.

If no operational-status row exists, the endpoint returns `200` with nullable
timestamps.

### `POST /sync/jira`

Runs Jira ingestion and downstream release and sprint recomputation. The
response reports fetched, inserted, updated, and skipped counts for releases,
sprints, issues, and history.

Important behavior:

- `409` means another sync is already running;
- Jira authentication failure returns `401`;
- other controlled sync or configuration failures return `400`;
- persisted and returned failures are sanitized;
- this is a privileged operator operation.

## Releases and issues

### `GET /releases`

Returns a paginated release list.

Query parameters:

- `project_key`: optional exact project filter;
- `skip`: offset, default `0`;
- `limit`: page size, default `50`, range `1..100`.

The response contains `items`, `skip`, `limit`, and `total`. An empty result is
a normal `200`.

### `GET /releases/{release_id}`

Returns one release or `404` when the identifier is unknown.

### `GET /releases/{release_id}/issues`

Returns the current issues associated with a release.

Query parameters:

- `skip`: offset, default `0`;
- `limit`: page size, default `50`, range `1..100`.

Issue records expose the stored fields used by analytics, including nullable
classification and Jira timestamps. The release is validated before the
paginated list is returned.

### `GET /issues/{jira_key}`

Returns one stored issue by Jira key or `404` when it is unknown.

## Release metrics and history

### `GET /releases/{release_id}/metrics`

Returns the latest stored release metric snapshot and its response artifacts.
The response includes ruleset identity, calculation provenance, metric values,
issue-key evidence, metric availability, thresholds, confidence breakdown,
biggest driver, recommendations, computation state, and snapshot age.

If the release exists without a snapshot, the endpoint returns `200` with
`snapshot_at: null`, `is_computed: false`, nullable metric values, and a
structured `NOT_COMPUTED` state. Partial confirmed-minimum counts can remain
available while percentages or confidence that require incomplete inputs are
`null`; consult each availability item's status, explanations, and missing Jira
keys.

### `GET /releases/{release_id}/charts`

Returns frontend-agnostic time series built from stored snapshots.

Query parameters:

- `limit`: maximum snapshots, default `500`, range `1..5000`;
- `from`: optional inclusive lower timestamp;
- `to`: optional inclusive upper timestamp.

`from > to` returns `400`. Each point contains `snapshot_at`, nullable `value`,
`ruleset_version`, and `version_boundary`. The response also includes metric
names, total point count, and the number of release gates.

### `GET /releases/{release_id}/snapshot-comparison`

Compares the latest snapshot with a selected baseline.

Query parameter:

- `baseline`: `previous`, `24h`, or `7d`; default `previous`.

No matching baseline returns `200` with `has_baseline: false`. Confidence delta
and contributors are unavailable when ruleset versions differ, classification
mappings differ, or required confidence is unavailable; `unavailable_reason`
explains why.

### `GET /releases/{release_id}/snapshot-change-history`

Returns stored change-history items.

Query parameter:

- `limit`: maximum items, default `100`, range `1..5000`.

Items expose their ruleset version, version boundary, confidence, delta,
primary driver, and any comparison-unavailable reason.

### `POST /releases/{release_id}/recompute`

Creates a new immutable release metric snapshot, computes its release signal,
and commits both in one transaction. It returns the release identifier,
snapshot time, ruleset version, and `status: "ok"`. An unknown release returns
`404`.

### `POST /releases/recompute-all`

Best-effort recomputation for every stored release. Each release is committed
independently. The structured response reports totals, elapsed time, and
sanitized per-release errors instead of aborting the whole batch on one
failure.

## Release signal

### `GET /releases/{release_id}/signal`

Returns the latest stored release signal and the metric snapshot it belongs to.
Current-version responses can include final signal, confidence, reasons,
structured reason details, release gates, critical risks, warnings, primary
risk, confidence breakdown, biggest driver, current risk aging, 24-hour
evidence, Release Outlook, and thresholds.

Important behavior:

- an existing release without a signal returns structured `200` data with a
  null signal rather than `404`;
- current uninterrupted risk age starts when the active blocker or
  high-severity condition became active; issue creation time is a separate age;
- when risk start cannot be proven from history, that age remains unavailable;
- the 24-hour comparison uses the latest snapshot at or before the boundary and
  does not invent a baseline;
- legacy ruleset results withhold unsupported current derived fields;
- confirmed hard-RED evidence can remain RED when other inputs are partial;
  otherwise incomplete confidence can produce `INCONCLUSIVE` Release Outlook.

## Sprints

### `GET /sprints`

Returns a paginated sprint list.

Query parameters:

- `project_key`: optional exact project filter;
- `state`: optional `active`, `closed`, or `future` filter;
- `skip`: offset, default `0`;
- `limit`: page size, default `50`, range `1..100`.

### `GET /sprints/current`

Returns the current active sprint as `item`. Optional `project_key` narrows the
lookup. When there is no matching active sprint, the endpoint returns `200`
with `item: null`.

### `GET /sprints/{sprint_id}`

Returns one sprint or `404` when the identifier is unknown.

### `GET /sprints/{sprint_id}/issues`

Returns a paginated list of current sprint-membership issues. Each item also
includes `in_initial_scope`, which is stored evidence and must not be inferred
by the client.

Query parameters:

- `skip`: offset, default `0`;
- `limit`: page size, default `50`, range `1..100`.

### `GET /sprints/{sprint_id}/metrics`

Returns the latest stored sprint snapshot, including ticket metrics,
issue-key evidence, metric availability, story-point coverage, workload
distribution, delivery-confidence status and explanations, component details,
confidence breakdown, biggest driver, recommendations, provenance, and ruleset
identity.

Delivery-confidence coverage states are explicit:

- empty sprint: `NOT_COMPUTED`, score `null`;
- below 50% pointed tickets: `INCONCLUSIVE`, score `null`;
- at least 50% but below 100%: `PARTIAL`, score returned when other required
  inputs are complete;
- 100%: `COMPUTED`, score returned without partial-coverage remarks.

Missing required status, duration, blocker classification, or sprint-history
inputs can make delivery confidence `INCONCLUSIVE` even when point coverage is
sufficient. Independently computable ticket metrics remain available. No story
points or missing classifications are imputed.

### `GET /sprints/{sprint_id}/snapshot-comparison`

Uses the same `baseline=previous|24h|7d` query contract as the release
comparison. Missing baselines and incompatible ruleset, classification, or
confidence states return structured unavailable comparisons rather than
invented deltas.

### `GET /sprints/{sprint_id}/snapshot-change-history`

Returns up to `limit` stored history items; `limit` defaults to `100` and ranges
from `1` to `5000`. Each item includes ruleset and version-boundary metadata.

### `POST /sprints/{sprint_id}/recompute`

Creates and commits one new immutable sprint metric snapshot. It returns the
sprint identifier, snapshot time, ruleset version, and `status: "ok"`. An
unknown sprint returns `404`.

## PDF reports

All report endpoints return `application/pdf` with an attachment filename.
Reports are built from stored artifacts through focused data-preparation,
document-template, chart, and PDF-rendering stages. They do not recompute
metrics or reinterpret historical results with current rules.

### `GET /reports/documentation.pdf`

Exports the built-in LighthousePM documentation report.

### `GET /releases/{release_id}/reports/overview.pdf`

Exports the combined overview report for a release and its project context.
An unknown release returns `404`.

### `GET /releases/{release_id}/reports/{depth}.pdf`

Exports a release report. `depth` must be `summary` or `full`; invalid values
return `422`, and an unknown release returns `404`.

### `GET /sprints/{sprint_id}/reports/{depth}.pdf`

Exports a sprint report. `depth` must be `summary` or `full`; invalid values
return `422`, and an unknown sprint returns `404`.

## Current limits

- One Jira project is configured per running instance.
- LighthousePM does not provide native user roles; the operator bearer token
  protects both reads and privileged operations when authentication is enabled.
- OpenAPI and interactive documentation are protected resources, not public
  bypasses.
- Metric and signal behavior is deterministic and rule-based. Routes validate
  and delegate; services own computation and response assembly.
- Historical APIs and reports use stored ruleset identity and provenance rather
  than recalculating old results under current rules.
