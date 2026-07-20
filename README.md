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
- [`ABOUT.md`](ABOUT.md) explains the product and its screens for users.
- [`desktop/README.md`](desktop/README.md) documents desktop packaging,
  installation, migration, recovery, and acceptance procedures.

If a summary in this README conflicts with `PRODUCT_RULES.md`, the product-rule
catalog is authoritative.

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

LighthousePM is a single service with a thin API layer:

```text
Jira -> jira_service -> sync_service -> database
                                      |
                                      +-> analytics_service -> metric snapshots
                                      +-> signal_service    -> release signals
                                                              |
                                                              +-> REST API / PDF reports / dashboard
```

Core responsibilities:

| Component | Responsibility |
|---|---|
| `jira_service` | Jira API requests and response normalization |
| `sync_service` | Ingestion orchestration and deterministic upserts |
| `analytics_service` | Release and sprint metric computation |
| `signal_service` | Release risk rules, readiness, and Release Outlook |
| FastAPI routes | Request validation and structured response mapping |
| PostgreSQL | Default backend storage |
| SQLite | Local and packaged desktop storage |
| React + TypeScript | Read-only dashboard over the backend API |

Business rules belong in services and `PRODUCT_RULES.md`, not in API routes,
React components, or PDF templates.

## Current product contracts

This section is a concise implementation summary. See `PRODUCT_RULES.md` for
complete formulas, boundaries, missing-data behavior, and evidence rules.

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

## REST API

All controllers return structured JSON except PDF export endpoints.

### Health and configuration

- `GET /health`
- `GET /admin/status`
- `GET /config/jira`
- `PUT /config/jira`
- `POST /config/jira/test`
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
- changelog aliases identify fix-version and sprint membership changes.

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
`20260720_0017`.

- Fresh databases are created through Alembic.
- Versioned databases upgrade to the single current head.
- Recognized pre-Alembic SQLite schemas are deterministically stamped at their
  actual historical revision and upgraded in order.
- A consistent SQLite backup is created before migration. For the current
  migration head its suffix is `.pre-20260720_0017.bak`.
- Unknown or partially migrated legacy schemas stop startup instead of being
  guessed or silently modified.
- Repeated startup at the current revision is idempotent.
- The current head keeps Jira `issues.status` and `issues.issue_type` nullable
  so missing source classifications remain explicit instead of being invented.

Manual migration from `backend/`:

```bash
alembic upgrade head
```

Schema changes require a new Alembic revision; `create_all` is not the
production migration mechanism.

## Local development

### Prerequisites

- Python 3.11 or newer
- Node.js and npm for the frontend or desktop shell
- PostgreSQL 14 or newer for the default backend setup, or SQLite for local
  file-backed development
- Docker Desktop when using Docker Compose

### Backend without Docker

```bash
cd backend
python -m pip install -e .
python -m pip install -r requirements-dev.txt
uvicorn app.main:app --reload --port 8000
```

The API documentation is available at `http://127.0.0.1:8000/docs` while the
development server is running.

Backend verification:

```bash
cd backend
pytest tests -q
ruff check app tests alembic
```

### Docker Compose

From the repository root:

```bash
docker compose up --build
```

The backend is exposed on `http://127.0.0.1:8000` and uses the Compose
PostgreSQL service.

### Frontend

```bash
cd frontend
npm install
npm run dev -- --host 127.0.0.1
```

Frontend verification:

```bash
cd frontend
npm test
npm run build
```

By default, browser development uses `http://localhost:8000`. Set
`VITE_API_BASE_URL` to override the backend URL.

### Desktop application

The Electron shell packages the FastAPI backend, migration scripts, frontend,
and local SQLite storage into one application. Build and release procedures
are documented in [`desktop/README.md`](desktop/README.md).

Common commands:

```bash
cd desktop
npm run dev
npm run package
npm run make
npm run verify:release
```

## Repository structure

```text
backend/
  alembic/           Database migrations
  app/
    api/             Thin FastAPI controllers
    db/              Database engine, startup, and migration orchestration
    models/          SQLAlchemy models
    repositories/    Persistence queries and writes
    schemas/         API contracts
    services/        Jira, sync, analytics, signal, and reporting logic
  tests/             Backend unit and integration tests
frontend/
  src/               React dashboard and assertion tests
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
3. the implementing service;
4. boundary, empty-data, partial-data, and historical-version tests;
5. API schemas and examples;
6. affected user and operational documentation.

The definition of done is deterministic logic, reproducible evidence, stable
structured APIs, and passing focused plus regression tests.
