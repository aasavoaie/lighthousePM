# LighthousePM

LighthousePM ingests Jira release and sprint data and turns it into
deterministic metrics, explainable risk signals, evidence-based release
outlooks, and structured reports.

The product does not use AI, machine learning, or hidden inference to decide
release health. Every derived result is calculated from explicit rules and can
be traced back to stored Jira evidence.

## Documentation map

- [`PRODUCT_RULES.md`](PRODUCT_RULES.md) is the source of truth for formulas,
  thresholds, availability rules, evidence, and ruleset versioning.
- [`AGENTS.md`](AGENTS.md) defines engineering constraints for AI agents
  working in this repository.
- [`HELPER.md`](HELPER.md) is the practical authenticated API and operations
  reference.
- [`UNIT_TEST_DOCS.md`](UNIT_TEST_DOCS.md) documents test coverage, focused
  commands, and environment-specific prerequisites.
- [`ABOUT.md`](ABOUT.md) explains the product and its screens for users.
- [`desktop/README.md`](desktop/README.md) documents desktop packaging,
  installation, migration, recovery, and acceptance procedures.

If a summary in this README conflicts with `PRODUCT_RULES.md`, the product-rule
document is authoritative.

## Product scope

LighthousePM currently supports:

- one configured Jira project per running instance;
- Jira releases, issues, sprints, and relevant changelog ingestion;
- deterministic release and sprint metric snapshots;
- rule-based release confidence, readiness gates, and final signals;
- sprint delivery confidence with explicit story-point coverage states;
- immutable, versioned historical results and comparisons;
- deterministic recommended actions;
- release and sprint PDF reports;
- a React dashboard and a packaged Windows desktop application.

Current non-goals include multi-project aggregation in one runtime, predictive
probabilities, statistical forecasting, microservices, and inferred Jira data.

## Architecture

LighthousePM remains one backend service with a thin API layer. Focused
application services separate computation, response assembly, and reporting
without introducing microservices or a generic abstraction framework:

```text
Jira -> jira_service -> sync_service -> repositories -> database
                                                    |
                                                    +-> analytics_service -> metric snapshots
                                                                            |
                                                                            +-> signal_service

FastAPI routes -> response/recompute/catalog services -> structured JSON
               -> reporting_service -> prepared data -> templates -> charts/PDF

React API client -> workspace hooks and page containers -> focused components
```

Core responsibilities:

| Component | Responsibility |
|---|---|
| `jira_service` | Jira API requests and response normalization |
| `sync_service` | Ingestion orchestration and deterministic upserts |
| `analytics_service` | Release and sprint metric computation |
| `signal_service` | Release risk rules, readiness, and Release Outlook |
| Response services | Release and sprint response assembly from stored artifacts |
| `metric_recompute_service` | Release and sprint recomputation orchestration |
| Metric catalog | Shared labels, units, formatting, thresholds, availability metadata, ordering, and feature participation |
| Reporting pipeline | Data preparation, document models, focused templates, chart rendering, and PDF rendering behind `reporting_service` |
| FastAPI routes | Request validation, dependency injection, service delegation, and HTTP error mapping |
| PostgreSQL | Default backend storage |
| SQLite | Local and packaged desktop storage |
| React + TypeScript | Authenticated dashboard, reporting, Jira settings, sync, and recomputation workflows |
| Frontend pages and hooks | Workspace data orchestration and page/container responsibility |
| Frontend components | Focused rendering and user interaction without metric computation |

Business rules belong in services and `PRODUCT_RULES.md`, not in API routes,
React components, or PDF templates.

## Current product contracts

This section is a concise implementation summary. See `PRODUCT_RULES.md` for
complete formulas, boundaries, missing-data behavior, and evidence rules.

### Metric catalog

`PRODUCT_RULES.md` remains the normative authority for product behavior.
[`backend/app/metric_catalog.py`](backend/app/metric_catalog.py) is the
machine-readable implementation authority for shared mechanical metadata; it
does not replace the explicit formulas in `analytics_service` or signal logic
in `signal_service`.

The protected `GET /metadata/metrics` endpoint exposes the current catalog and
ruleset versions plus deterministic release and sprint definitions. The
frontend loads it once inside the authentication boundary and uses a generated
backend-owned fallback if the request fails or the response is incompatible.
Reports use the same catalog labels, units, ordering, and formatting rules.
Contract tests prevent the API serialization, frontend fallback, threshold
consumers, and report presentation from drifting apart.

Catalog metadata never reinterprets immutable historical results. Stored
values, provenance, availability, thresholds, and ruleset identity remain
authoritative for historical responses and reports.

### Release metrics

Release snapshots include:

- open blockers;
- open high-severity bugs;
- scope completed percentage and completed ticket count;
- seven-day scope churn, additions, and removals;
- median cycle time;
- reopen events per 100 eligible tickets, including repeated events from the same ticket;
- confidence score, confidence breakdown, and biggest driver;
- metric availability and Jira issue-key evidence.

The final release signal is the worse severity produced by:

1. explicit hard RED/YELLOW rules; and
2. the approved weighted confidence-score band.

Every signal includes human-readable reasons, structured reason details,
thresholds, release gates, current risk evidence, and ruleset provenance.

### Sprint ticket-scope metrics

The compatibility field `committed_scope` means **Current sprint scope**: the
number of distinct tickets currently linked to the sprint at snapshot time. It
does not claim to reconstruct the sprint-start commitment. Empty current scope
is unavailable rather than zero.

`completed_scope_pct` is the percentage of that current ticket scope whose
current status is configured as done. It does not use story points. Empty scope
is unavailable, and a missing ticket status makes the percentage partial and
unavailable with the affected Jira keys exposed as evidence.

`in_progress_count` counts current sprint tickets whose known status is in the
configured in-progress set. `not_started_count` counts current sprint tickets
whose known, non-empty status is in neither the configured done nor in-progress
set. Missing statuses are excluded from both counts and make the returned
confirmed-minimum values `PARTIAL`. Empty current scope returns `null` with
`NOT_COMPUTED`.

The compatibility field `rollover_count` has the user-facing meaning
**Unfinished closed-sprint scope**. It applies only to closed sprints and counts
current sprint-membership tickets whose known current status is not done. It
does not prove that those tickets entered another sprint. Active, future, or
unknown-state sprints return `null` with `NOT_APPLICABLE`; a closed sprint with
empty current scope returns `null` with `NOT_COMPUTED`. Missing statuses are
excluded and make the confirmed-minimum count `PARTIAL`.

### Sprint delivery confidence

Sprint Delivery Confidence uses these stored component weights:

| Component | Weight |
|---|---:|
| Progress alignment | 40% |
| Velocity fit | 30% |
| Blocker health | 20% |
| Scope stability | 10% |

Story points are never imputed. Coverage controls the response state:

| Story-point coverage | Delivery-confidence result |
|---|---|
| Empty sprint | `NOT_COMPUTED`, score `null` |
| Below 50% | `INCONCLUSIVE`, score `null` |
| At least 50% but below 100% | `PARTIAL`, score returned with explanations |
| 100% | `COMPUTED`, score returned without partial-coverage remarks |

Meeting the story-point threshold is necessary but not sufficient. Delivery
confidence also requires:

- a non-empty status for every pointed current-sprint ticket;
- complete blocker classification across the current sprint scope;
- valid sprint start and end times with `end > start`; and
- complete sprint-membership changelog history for every synchronized ticket
  in the sprint's Jira project.

If any required non-point input is missing, delivery confidence is
`INCONCLUSIVE` and its score, component breakdown, and biggest driver are
unavailable. Explanations identify the affected input and sorted Jira keys.
Missing or invalid duration never receives a healthy elapsed-time,
remaining-time, or remaining-capacity fallback. Independently computable
ticket metrics remain available.

Ticket-count metrics remain available when they do not depend on aggregated
story points. Partial point-based calculations use only tickets with valid
story points and expose the excluded Jira keys.

### Sprint workload distribution

Workload concentration is calculated from active current-sprint story points
by the backend and stored with the sprint snapshot. Active status uses the
configured done-status classification; clients do not maintain a separate
status list. Null or blank assignees are grouped as `Unassigned`, while an
assigned user without a stable Jira identifier uses a deterministic display-
name fallback and makes the result `PARTIAL`.

Below `50%` current-sprint story-point coverage the result is `INCONCLUSIVE`.
From `50%` to below `100%`, only pointed active tickets are included and the
result lists excluded keys as `PARTIAL`. At `100%`, the complete active scope
is used. No active work is `NOT_APPLICABLE`; a zero-point denominator is
`NOT_COMPUTED`. Concentration is the top assignee's share of included active
story points, rounded to two decimals. Below `35%` is healthy, `35%` through
`50%` is watch, and above `50%` is critical.

The API exposes the percentage, availability, explanations, top-assignee
details, per-assignee totals, and sorted Jira-key evidence. Recommendations,
reports, and the frontend consume this stored result rather than recalculating
it.

### Risk aging

Issue age and current uninterrupted risk age are separate facts:

- issue age starts at Jira issue creation;
- risk age starts when the current blocker or high-severity condition became
  active;
- an unprovable risk start remains unavailable and is never replaced with a
  local database timestamp.

The API and reports expose the timestamps, history-completeness state, and
explanations used for risk-aging results.

### Release Outlook

Release Outlook summarizes the latest stored evidence:

- current confidence and final signal;
- passed and failed release gates;
- confidence change against the latest available 24-hour baseline;
- calendar days remaining until the Jira release date; and
- active hard RED and YELLOW conditions.

It is not a forecast and does not claim a probability, predicted future
confidence, or chance of meeting a release target.

### Ruleset versioning and history

- Current derived results use integer `ruleset_version` values.
- Version `0` identifies legacy results without an explicit ruleset.
- Version `1` identifies the approved Phase 0 contract.
- Version `2` identifies the approved Phase 2 metric-contract hardening.
- Metric snapshots and release signals are immutable.
- Recompute creates a new metric snapshot and an append-only signal result.
- Historical derived values are read from their stored artifacts, not
  recalculated with current rules.
- APIs, charts, comparisons, and reports expose ruleset versions and mark
  version boundaries.
- Cross-version comparisons are unavailable instead of mixing incompatible
  rules.

## Data flow

1. `POST /sync/jira` validates the configured Jira connection.
2. Jira releases, issues, sprints, and relevant changelog entries are
   normalized and upserted.
3. Release and sprint metrics are recomputed into new immutable snapshots.
4. A release signal is stored for each new release metric snapshot.
5. APIs and PDF reports read the stored results and their provenance.

Sync failures are sanitized before they are persisted or returned. Operational
status records the latest successful and failed sync times and the latest
metric and signal recomputations.

## Data model

Primary tables:

| Table | Purpose |
|---|---|
| `releases` | Jira release/version metadata |
| `issues` | Latest normalized Jira issue state and Jira timestamps |
| `issue_history` | Relevant Jira field changes |
| `sprints` | Jira sprint metadata |
| `issue_sprints` | Issue-to-sprint membership |
| `metric_snapshots` | Immutable release metric results and provenance |
| `sprint_metric_snapshots` | Immutable sprint metric results and provenance |
| `release_signals` | Append-only release signals and stored evidence |
| `operational_status` | Sync and recomputation status markers |
| `jira_project_sync_state` | Per-project Jira sync cursor, status, failure, and latest result markers |

## REST API

All controllers return structured JSON except PDF export endpoints.
FastAPI routes validate inputs and delegate to focused application services;
metric and sprint response assembly and report construction do not live in the
route modules. OpenAPI provides the runtime mechanical endpoint schema, while
[`HELPER.md`](HELPER.md) provides operational guidance.

### Health and configuration

- `GET /health`
- `GET /metadata/metrics`
- `GET /admin/status`
- `GET /config/jira`
- `PUT /config/jira`
- `POST /config/jira/test`
- `GET /sync/jira/status`
- `POST /sync/jira`

### Releases

- `GET /releases`
- `GET /releases/{release_id}`
- `GET /releases/{release_id}/issues`
- `GET /issues/{jira_key}`
- `GET /releases/{release_id}/metrics`
- `GET /releases/{release_id}/charts`
- `GET /releases/{release_id}/signal`
- `GET /releases/{release_id}/snapshot-comparison`
- `GET /releases/{release_id}/snapshot-change-history`
- `POST /releases/{release_id}/recompute`
- `POST /releases/recompute-all`

Release charts accept `limit`, `from`, and `to` query parameters. Comparison
endpoints accept `baseline=previous|24h|7d`.

### Sprints

- `GET /sprints`
- `GET /sprints/current`
- `GET /sprints/{sprint_id}`
- `GET /sprints/{sprint_id}/issues`
- `GET /sprints/{sprint_id}/metrics`
- `GET /sprints/{sprint_id}/snapshot-comparison`
- `GET /sprints/{sprint_id}/snapshot-change-history`
- `POST /sprints/{sprint_id}/recompute`

Sprint lists accept project, state, and pagination filters defined by the
FastAPI schema.

### PDF reports

- `GET /reports/documentation.pdf`
- `GET /releases/{release_id}/reports/overview.pdf`
- `GET /releases/{release_id}/reports/{depth}.pdf`
- `GET /sprints/{sprint_id}/reports/{depth}.pdf`

Report `depth` is `summary` or `full`.

## API response guarantees

### Metric responses

Release and sprint metric responses expose:

- `ruleset_version`, `ruleset_label`, and `calculation_provenance`;
- snapshot time, age, and computation state;
- metric values and exact issue-key evidence;
- metric-level availability and unavailable reasons;
- stored confidence artifacts, recommendations, and biggest driver.

Each metric-availability item includes authoritative `status`, `explanations`,
and sorted `missing_issue_keys` while retaining the compatibility fields
`available`, `reason`, and `depends_on`. Partial count metrics return confirmed
minimum values; percentages whose denominator classification is incomplete
return `null`.

Seven-day release scope churn uses the stored snapshot time as an inclusive
window boundary. Its denominator is the distinct union of current release
scope and tickets with confirmed additions or removals. Changelog completeness
is evaluated across synchronized tickets in the configured Jira project. When
that history is incomplete, added and removed counts remain confirmed minima,
the churn percentage is `null`, and availability identifies the missing Jira
keys. An absence of changelog rows is not itself incomplete history.

If blocker or high-severity-bug classification is partial, or the scope-churn
percentage is unavailable because project changelog ingestion is incomplete,
release confidence is `null`. A confirmed hard-RED condition still returns RED;
otherwise the signal and Release Outlook are `INCONCLUSIVE`. Snapshot confidence
comparisons are unavailable with an explicit reason while either snapshot is
inconclusive.

An existing entity with no snapshot returns `200` with a structured
`NOT_COMPUTED` response and nullable derived values. Unknown entity IDs return
`404`.

### Signal responses

A release signal response identifies its exact `metric_snapshot_id` and
`ruleset_version`. It includes stored confidence, reasons, gates, risk-aging
evidence, 24-hour evidence, and Release Outlook. A legacy result is explicitly
labelled or has unsupported derived fields withheld.

### Historical responses

Chart points and history items include `ruleset_version` and
`version_boundary`. Snapshot comparisons expose both ruleset versions. When
the versions differ, comparison values are unavailable with an explicit
reason.

### Metric metadata responses

`GET /metadata/metrics` returns release and sprint definitions in deterministic
display order. Each definition includes its stable key, API field and location,
label, description, category, unit, formatting rule, thresholds, availability
dependencies and evidence paths, feature participation, and ruleset version.
The response contains no credentials or deployment configuration.

## Configuration

Copy the example configuration:

```bash
cp backend/.env.example backend/.env
```

The complete list and defaults are in [`backend/.env.example`](backend/.env.example).
For Jira sync, configure at least:

- `JIRA_BASE_URL`
- `JIRA_USER_EMAIL`
- `JIRA_API_TOKEN`
- `JIRA_PROJECT_KEY`
- `JIRA_SYNC_ENABLED=true`

Field mappings are explicit per Jira instance:

- `JIRA_FIELD_SEVERITY` defaults to `priority`;
- `JIRA_FIELD_RELEASE` defaults to `fixVersions`;
- `JIRA_FIELD_SPRINT` identifies the sprint custom field;
- `JIRA_FIELD_STORY_POINTS` identifies the story-point field;
- `JIRA_FIELD_BLOCKER` optionally identifies an explicit blocker flag;
- changelog aliases identify fix-version and sprint membership changes; the
  configured release and sprint field identifiers are always recognized too.

Jira workflow classifications are also explicit, comma-separated settings:

- `JIRA_DONE_STATUSES` and `JIRA_IN_PROGRESS_STATUSES` classify workflow status;
- `JIRA_HIGH_SEVERITY_VALUES` and `JIRA_BUG_ISSUE_TYPES` classify high-severity bugs;
- `JIRA_BLOCKER_ISSUE_TYPES`, `JIRA_BLOCKER_SEVERITY_VALUES`, and
  `JIRA_BLOCKED_STATUSES` provide blocker fallbacks when no explicit blocker field is mapped.

Values are trimmed, compared case-insensitively, and deduplicated. Done and
in-progress classifications must not overlap. The first four settings above
must be non-empty; invalid updates are rejected and invalid startup
configuration stops the service. Snapshot comparisons are unavailable when
the effective Jira classifications differ between snapshots.

Scheduled sync is disabled when `JIRA_SYNC_INTERVAL_SECONDS=0`. Manual sync is
still available when Jira sync itself is enabled.

## Database migrations

Application startup runs the Alembic migration chain before accepting API
requests or starting scheduled work. The current single head is
`20260727_0022`.

Alembic is the only runtime schema authority for both PostgreSQL and SQLite.
Application startup does not use `Base.metadata.create_all()` and does not run
compatibility `ALTER TABLE`, `CREATE INDEX`, or other schema-repair statements
outside ordered Alembic revisions. `create_all()` is limited to isolated test
fixtures.

- Fresh databases are created through Alembic.
- Versioned databases upgrade to the single current head.
- Recognized unversioned schemas are deterministically stamped at their actual
  historical revision and upgraded in order.
- Before migration, a consistent SQLite backup is written to a unique
  temporary file beside the active database, flushed and closed, and then
  atomically published. For the current migration head its canonical suffix is
  `.pre-20260727_0022.bak`.
- Unknown or partially migrated legacy schemas stop startup instead of being
  guessed or silently modified.
- Repeated startup at the current revision is idempotent.
- The current head keeps Jira `issues.status` and `issues.issue_type` nullable
  so missing source classifications remain explicit instead of being invented.

Every prior revision retained in the single Alembic chain is a supported
versioned upgrade source. For the current chain, this is `20260407_0001`
through `20260726_0021`. Recognized unversioned SQLite sources are limited to
the explicit legacy-shape registry, currently `20260407_0001` through
`20260716_0010`; other unversioned shapes fail closed.

The automated upgrade matrix derives its sources from the Alembic graph and
legacy registry. It verifies migration to head, representative data
preservation, current schema shape, SQLite pre-migration backup creation, and
idempotent restart. The complete versioned matrix must run on file-backed
SQLite and a real PostgreSQL instance. Migration-specific downgrade tests are
additional checks; downgrade is not a supported desktop recovery path.

Start PostgreSQL with the loopback-only Compose override documented under
Docker Compose below, using synthetic secret files. Then run the PostgreSQL
gate with the same database password:

```bash
cd backend
MIGRATION_TEST_POSTGRES_ADMIN_URL=postgresql+psycopg://postgres:<password>@127.0.0.1:5432/postgres \
  make postgres-test
```

The required runner sets `LIGHTHOUSE_REQUIRE_POSTGRES_INTEGRATION=1`, verifies
the administrative connection, and fails when no PostgreSQL tests are
collected or any required test skips. Tests create only
`lighthouse_migration_*` and `lighthouse_startup_*` databases and refuse to
drop anything else. The normal `lighthouse` application database is never a
test target.

Migration acceptance also runs through the application startup boundary. Clean
startup tests begin without a database or parent directory and verify current
head, health readiness, structured empty API responses, and the absence of an
unnecessary migration backup. Existing-database tests verify current and older
states, representative related data through public APIs, required SQLite backup
behavior, and idempotent restart.

Application-level coverage includes file-backed SQLite, real PostgreSQL, one
recognized unversioned SQLite database, and the desktop backend entry point
running against temporary storage. Exhaustive per-revision coverage remains in
the Phase 3.3 migration matrix; the application tests use representative source
states to exercise startup, readiness, authentication, and API access.

SQLite migration backup publication is fail-closed. Alembic stamping and
migration begin only after the temporary backup has been flushed, closed, and
atomically published at the canonical `.pre-<revision>.bak` path. A failed copy
or publication stops startup, leaves the source at its original revision, and
does not expose a new canonical backup. Temporary files are non-authoritative
and are never reused as backups. An existing canonical backup is not
overwritten.

Every new or existing canonical migration backup is validated read-only before
publication or reuse. Validation requires a regular SQLite file,
`PRAGMA integrity_check` equal to `ok`, a known Alembic revision or recognized
legacy schema, a source revision matching the active pre-migration database,
and a supported source-to-target revision relationship. Failure stops startup
before Alembic changes either database and reports the backup path and failed
rule. The invalid file is preserved rather than deleted or overwritten.

Automatic migration backups remain a manual recovery format. The packaged
local validator must report integrity, source revision, revision identity type,
filename target revision, installed-chain compatibility, and a final `VALID`
or `INVALID` result before recovery instructions allow the file to replace the
active database.

Run the packaged validator from the backend executable directory:

```powershell
.\lighthousepm-backend.exe --validate-sqlite-backup `
  "$env:APPDATA\LighthousePM\data\lighthouse.db.pre-20260727_0022.bak" `
  --migration-backup
```

The command prints one structured JSON result and exits nonzero when `status`
is `INVALID`.

### Settings backup validation

Settings Backup uses manifest version `2`. Its completed manifest records the
application identity, format version, creation time, allowed relative payload
paths, byte sizes, SHA-256 digests, and database revision identity. The database
payload is a consistent standalone SQLite file; version 2 does not carry WAL or
SHM files. The manifest is published last so incomplete backup directories are
not selectable.

Settings Restore accepts only a complete version-2 manifest. Version 1 lacks
stored checksums and is preserved but rejected as an unverifiable legacy
format. Missing, malformed, non-positive, unknown, and future versions also
fail closed.

Before the backend is stopped or active files are changed, restore preflight
checks the manifest identity and version, fixed path allowlist, regular-file
status, sizes and hashes, SQLite integrity and supported revision, UTF-8
configuration structure, and encrypted-token decryptability. Any failure
leaves the running backend and all active files unchanged and identifies the
selected backup and failed rule.

After successful preflight, restoring a database removes stale active WAL and
SHM files, optional configuration and token files are replaced only when
included, and backend restart passes through the normal migration-readiness
gate. Transactional rollback after a failure during validated replacement is
defined below.

### Transactional desktop storage operations

Settings Restore, Clear Data, and Factory Reset use one operation lock and a
versioned recovery journal under
`%APPDATA%\LighthousePM\recovery\<operation-id>\`. The backend must stop and
confirm process exit before any active-file mutation; a fixed delay alone is
not sufficient.

Before mutation, affected active paths are captured with their original
presence, sizes, and SHA-256 digests. The journal is atomically published and
updated through deterministic states. Success requires the requested file
outcome, backend readiness, and operation-specific verification. Recovery data
is removed only after success is confirmed.

Replacement, deletion, or restart failure restores the previous state and
restarts it through the same readiness gate. The requested operation still
reports failure with `previous state restored`. If rollback or its restart
fails, the recovery directory and diagnostics remain, and the backend and
workspace stay closed.

Before normal backend startup, Electron checks for one unfinished journal and
recovers it deterministically. Missing, multiple, malformed, or checksum-invalid
recovery state fails closed. Recovery journals are internal and cannot be
selected by Settings Restore. This mechanism never automatically restores a
migration `.pre-<revision>.bak` after schema migration failure.

Clear Data retains configuration, encrypted token, logs, and automatic
migration backups while replacing the active database set with a fresh empty
current-head database. Factory Reset also removes configuration, token, and
previous logs, retains automatic migration backups, and returns to first-run
state. Both operations roll back their previous state if readiness fails.

Automated lifecycle tests cover backup/restore round trips, optional payloads,
every replacement and rollback boundary, restart failures, interrupted-journal
recovery, Clear Data and Factory Reset success and rollback, concurrent
operation rejection, and exact user-facing outcomes. They use isolated
temporary user data and representative upgrade sources; the exhaustive Alembic
source matrix remains separate.

Manual migration from `backend/`:

```bash
alembic upgrade head
```

Schema changes require a new ordered Alembic revision supporting the configured
database dialects. An unknown, partial, inconsistent, multi-head, or failed
migration state prevents API readiness and scheduled work.

For the packaged desktop application, Electron starts the managed backend and
waits for a successful health response before loading the workspace. Backend
startup validates configuration, migrates the database, and only then starts
scheduled work and reports healthy. The same gate applies after restore, Clear
Data, Factory Reset, and any other desktop-managed backend restart. A migration
failure leaves the workspace closed, does not start scheduled work, and directs
the user to the desktop backend log; it never triggers an automatic data reset.

## Local development

### Prerequisites

- Python 3.11 (the version used to generate and validate dependency locks)
- Node.js 22 and npm for the frontend or desktop shell
- PostgreSQL 14 or newer for the default backend setup, or SQLite for local
  file-backed development
- Docker Desktop when using Docker Compose

### Backend without Docker

```bash
cd backend
python -m pip install --require-hashes -r requirements/linux-dev.lock
python -m pip install --no-deps --no-build-isolation -e .
python -m pip check
DEPLOYMENT_MODE=local-browser APP_HOST=127.0.0.1 \
  uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

On Windows, use `requirements/windows-dev.lock` in place of
`requirements/linux-dev.lock`. To regenerate the locks for the current native
platform with Python 3.11, run `python scripts/compile_python_locks.py`; add
`--upgrade` only for an intentional dependency upgrade. `make locks` and
`make locks-upgrade` are equivalent convenience targets. Linux and Windows
locks must each be generated on their native platform, and every resulting
diff must be reviewed. `backend/pyproject.toml` remains the source for direct
dependency ranges. CI repeats non-upgrading regeneration on native Linux and
Windows runners and rejects any diff in the corresponding lock files.

Direct-dependency inventories are deterministic and package-specific:

```bash
cd backend
make dependency-check

cd ../frontend
npm run check:dependencies

cd ../desktop
npm run check:dependencies
```

The backend command maps maintained Python imports to the distributions in
`pyproject.toml` and runs `pip check`. The frontend and desktop commands verify
source imports, configured build tools, and Electron Forge makers against the
applicable `package.json`, then run `npm ls --depth=0`. Standard-library and
Node built-in modules, local imports, generated output, and internal type-only
imports are excluded explicitly. An undeclared third-party dependency, an
incorrect runtime/dev classification, or a broken installed tree fails the
command.

The API documentation is available at `http://127.0.0.1:8000/docs` while the
development server is running.

`DEPLOYMENT_MODE` must be one of `desktop`, `local-browser`, or `docker`, and
`APP_HOST` must match the host passed to the server. Direct backend development
uses `local-browser` and loopback by default. The Electron and Docker launch
paths set their deployment identity and effective bind host automatically.
Desktop mode additionally requires managed SQLite storage and empty
`CORS_ORIGINS`. Browser modes accept only exact HTTP or HTTPS origins; wildcard
origins and origins containing paths, credentials, queries, or fragments stop
startup before migration.

API authentication is required in `prod`, for every non-loopback bind, and in
desktop or Docker mode. Configure exactly one of `LIGHTHOUSE_API_TOKEN` or
`LIGHTHOUSE_API_TOKEN_FILE`; a required missing token or an invalid/conflicting
source stops startup before migration and scheduled work. Loopback-only `dev`
or `test` local-browser mode may remain anonymous, but a configured token
protects it immediately. All routes except `/health` use
`Authorization: Bearer <token>`. Browser deployments request the token from the
operator and retain it only in page memory; reload or page close clears it.

Every registered route has one explicit security class. `GET /health` is the
only public route. Dashboard, reporting, OpenAPI, and documentation reads are
protected reads. Jira configuration, administration status, Jira sync, and
release or sprint recomputation are privileged operations. The same operator
token authorizes both protected classes; LighthousePM does not provide native
roles in this release. Privileged responses use `Cache-Control: no-store`, and
their validation and HTTP errors suppress submitted bodies and redact
credential values.

Jira credentials follow the same direct-value or file-source rule through
`JIRA_API_TOKEN` and `JIRA_API_TOKEN_FILE`. In non-Electron deployments the
Settings API never persists a Jira token: Save writes nonsecret fields only,
while Test Connection may use the entered token for that request. Update the
external token source and restart the backend for a durable change. Electron
continues to persist its Jira token with operating-system-backed `safeStorage`.

Production PostgreSQL connections configure exactly one of
`POSTGRES_PASSWORD` or `POSTGRES_PASSWORD_FILE` and omit the password from
`DATABASE_URL`; the backend inserts it into the effective connection URL in
memory. Passwords embedded in `DATABASE_URL` are accepted only for loopback
`dev` or `test` compatibility and are rejected in production and Docker mode.

Backend verification:

```bash
cd backend
make quality
```

The equivalent canonical commands run normal backend tests with PostgreSQL and
Docker acceptance excluded, check every maintained backend Python file, type
check the application boundary, verify direct and installed dependencies, and
exercise deterministic SQLite migration and startup upgrades. The
environment-backed PostgreSQL and Docker gates are run separately.

The stable CI merge-readiness jobs are `backend-quality`,
`postgres-integration`, `frontend`, `desktop`, and `docker-security`. Repository
CI defines these independently so an owner can require their exact names in
branch protection; LighthousePM does not modify repository-external branch
protection settings automatically.

Use `make migration-check` when only the SQLite migration and startup-upgrade
matrix needs to be verified. Use `make docker-test` from `backend` to run the
required static and runtime Docker security suite. The required runner rejects
missing Docker-marked runtime coverage and any skipped runtime test.

Repository hygiene validates the committed Git index, not platform-specific
working-tree checkout endings: tracked text must be normalized to LF, while
binary and no-line-ending content remain supported. Every stable CI job runs
the verification-clean hygiene check as an `always()` final step so an earlier
failure cannot hide generated-content or line-ending drift.

The authoritative Phase 6 completion matrix and evidence-report template are
in [`UNIT_TEST_DOCS.md`](UNIT_TEST_DOCS.md#phase-6-completion-matrix). A local
equivalent does not prove that its GitHub Actions job passed: completion
reports must separate locally passed, environment-dependent, CI-only or
pending, and warning evidence.

Run the complete Phase 4 security acceptance gate from the desktop directory:

```bash
cd desktop
npm run verify:security
```

This command runs the full backend tests and lint, frontend tests and production
build, and desktop tests. When Docker is available it also requires the
isolated Compose authentication and configuration-write smoke test. CI jobs
that are expected to provide Docker must set
`LIGHTHOUSE_REQUIRE_DOCKER_SECURITY=1`; the gate then fails if the Docker CLI
or daemon is unavailable. `npm run release:windows` runs the same security gate
before building and verifying release artifacts. All acceptance credentials,
configuration, containers, and volumes are synthetic and disposable.

### Docker Compose

From the repository root:

```bash
mkdir -p .secrets .config
cp backend/docker.env.example .config/backend.env
python -c "import secrets; print(secrets.token_urlsafe(32))"
# Save independently generated values as .secrets/lighthouse_api_token and
# .secrets/postgres_password, then run:
LIGHTHOUSE_CONFIG_DIR=./.config \
LIGHTHOUSE_API_TOKEN_FILE=./.secrets/lighthouse_api_token \
POSTGRES_PASSWORD_FILE=./.secrets/postgres_password \
docker compose up --build
```

The backend listens on `0.0.0.0:8000` inside its container but is published to
`http://127.0.0.1:8000` on the host by default. `LIGHTHOUSE_BACKEND_PORT` may
change the host port without changing the loopback-only binding. Docker mode
always requires the API bearer token. Compose mounts the host token file at
`/run/secrets/lighthouse_api_token`; it does not place that token value in the
rendered environment. Keep the host file private and outside version control.
The PostgreSQL password is likewise mounted at
`/run/secrets/postgres_password` for both containers. The base Compose file
does not load `backend/.env`, contain a database password, or render either
secret value. `.config/backend.env` is a writable, gitignored, nonsecret file
used for deterministic Settings updates across container restarts.

An existing `pgdata` volume created by the earlier Compose configuration still
has its original database password; changing the secret file alone does not
change that stored PostgreSQL role password. Start that volume once with its
current password in the secret file, run `docker compose exec postgres psql -U
postgres -d lighthouse`, use the interactive `\password postgres` command,
then place the same new value in `.secrets/postgres_password` and restart the
services. The interactive command avoids putting the new password in shell
history. Fresh volumes need no migration step.

Jira sync is disabled in the base configuration. To enable it, fill the
nonsecret Jira connection and mapping fields in `.config/backend.env`, set
`JIRA_SYNC_ENABLED=true`, save the Jira token in
`.secrets/jira_api_token`, and include the Jira override:

```bash
LIGHTHOUSE_CONFIG_DIR=./.config \
LIGHTHOUSE_API_TOKEN_FILE=./.secrets/lighthouse_api_token \
POSTGRES_PASSWORD_FILE=./.secrets/postgres_password \
JIRA_API_TOKEN_FILE=./.secrets/jira_api_token \
docker compose -f docker-compose.yml -f docker-compose.jira.yml up --build
```

PostgreSQL is not published to the host by the base configuration. Administer
it through the private Compose network:

```bash
docker compose exec postgres psql -U postgres -d lighthouse
```

When a host database connection is required, enable the separate loopback-only
override:

```bash
LIGHTHOUSE_CONFIG_DIR=./.config \
LIGHTHOUSE_API_TOKEN_FILE=./.secrets/lighthouse_api_token \
POSTGRES_PASSWORD_FILE=./.secrets/postgres_password \
  docker compose -f docker-compose.yml -f docker-compose.postgres-local.yml up --build
```

This publishes PostgreSQL only at
`127.0.0.1:${LIGHTHOUSE_POSTGRES_PORT:-5432}`. The base and override files do
not publish either service on an IPv4 or IPv6 wildcard address. Both services
use a project-scoped bridge network, and Compose-generated names allow isolated
project instances without fixed-container-name collisions.

The default browser origins are `http://127.0.0.1:5173` and
`http://localhost:5173`. Override them with a comma-separated exact-origin
list in `LIGHTHOUSE_CORS_ORIGINS`; wildcard origins are rejected. Publishing
the backend on a non-loopback interface is an explicit security-boundary
change and is unsupported without the production authentication, restrictive
CORS, TLS reverse-proxy, and network controls defined in the security contract.

### Frontend

```bash
cd frontend
npm ci
npm run dev -- --host 127.0.0.1
```

Frontend verification:

```bash
cd frontend
npm run check:dependencies
npm test
npm run build
```

`npm test` is the aggregate frontend gate. It runs dependency-inventory and
assertion-runner contracts, every deterministic `.test.ts` logic assertion,
and the Vitest `.component.test.tsx` component suite. The assertion runner
fails if no source tests are found, compilation produces no executable tests,
the source and compiled inventories differ, or an assertion fails. The
component suite uses React Testing Library, `user-event`, JSDOM, and Axe to
cover authentication, loading, empty and error states, project-switch races,
forms, reports, and dialog behavior. Both layers mock the API boundary and
require no backend process, API token, Jira credentials, or network service.

Use `npm run test:assertions` or `npm run test:components` for a focused layer;
`npm test` remains the required local and CI entry point.

`npm run build` is a separate TypeScript and Vite production-build gate. Build
warnings remain visible; the existing Vite bundle-size warning is not by itself
a failure. CI runs these commands in the independently visible `frontend` job
on Ubuntu with Node.js 22 after installing the committed lockfile with `npm ci`.

The offline frontend metric-catalog fallback is generated from the backend
catalog. After an approved catalog change, regenerate it before verification:

```bash
cd backend
python scripts/export_metric_catalog.py
```

Backend contract tests fail when the generated file differs from the public
catalog serialization.

By default, browser development uses `http://localhost:8000`. Set
`VITE_API_BASE_URL` to override the backend URL.

### Desktop application

The Electron shell packages the FastAPI backend, migration scripts, frontend,
and local SQLite storage into one application. Build and release procedures
are documented in [`desktop/README.md`](desktop/README.md).

Desktop security and lifecycle tests use Node's built-in test runner with
mocked Electron boundaries. They cover the exact preload IPC surface, trusted
sender and payload validation, BrowserWindow and session hardening, permission
denial, navigation controls, backend readiness and exit handling, confirmed
shutdown, recovery ordering, and escaped startup/error documents. They do not
launch Electron or constitute installer acceptance.

Common commands:

```bash
cd desktop
npm run dev
npm run package
npm run make
npm run verify:release
```

The focused Windows desktop-validation gate builds and exercises only the real
packaged backend; it does not build React, Electron, a ZIP, or an installer:

```bash
cd backend
python -m pip install --require-hashes -r requirements/windows-dev.lock
python -m pip install --no-deps --no-build-isolation -e .
python -m pip check

cd ../desktop
npm ci
npm run check:dependencies
npm run lint
npm run test:node
npm run build:backend
npm run smoke:backend
```

Use `npm test` for the local aggregate of desktop lint and Node tests, or
`npm run test:node` while iterating on executable desktop behavior. The desktop
runner discovers `.test.cjs` files deterministically and fails if discovery is
empty.

The smoke command starts `lighthousepm-backend.exe` on a dynamic loopback port
with disposable SQLite data and a synthetic token. It requires healthy startup,
anonymous rejection, and an authenticated structured empty releases response,
then confirms process shutdown and removes its temporary data. CI runs the same
commands in the stable `desktop` job on Windows with Node.js 22 and Python 3.11.

## Repository structure

```text
backend/
  alembic/           Database migrations
  app/
    api/             Thin FastAPI controllers
    db/              Database engine, startup, and migration orchestration
    metric_catalog.py  Canonical mechanical metric metadata
    models/          SQLAlchemy models
    repositories/    Persistence queries and writes
    schemas/         API contracts
    services/        Jira, sync, analytics, signal, response, catalog, and reporting logic
  scripts/           Deterministic maintenance and export tools
  tests/             Backend unit and integration tests
frontend/
  src/
    components/      Focused UI components and presentation helpers
    generated/       Backend-generated metric-catalog fallback
    hooks/           Workspace data and mutation orchestration
    pages/           Top-level page containers
desktop/
  src/               Electron main and preload processes
  scripts/           Packaging, assets, verification, and acceptance tools
PRODUCT_RULES.md      Normative product-rule catalog
```

## Change workflow

A change to a metric, signal, threshold, availability rule, classification, or
output meaning must update together:

1. `PRODUCT_RULES.md`;
2. the centralized ruleset version when behavior changes;
3. the backend metric catalog when shared mechanical metadata changes;
4. the implementing service;
5. the generated frontend catalog fallback;
6. boundary, empty-data, partial-data, drift, and historical-version tests;
7. API schemas and examples;
8. affected user and operational documentation.

The definition of done is deterministic logic, reproducible evidence, stable
structured APIs, and passing focused plus regression tests.
