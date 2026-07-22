# Test and Verification Guide

This document describes durable LighthousePM coverage areas, commands, and
environment prerequisites. It deliberately does not record test totals or
per-file counts because those become stale whenever coverage changes.

Product behavior is authoritative in [`PRODUCT_RULES.md`](PRODUCT_RULES.md).
Development and deployment commands are summarized in
[`README.md`](README.md), while packaged Windows acceptance is detailed in
[`desktop/README.md`](desktop/README.md).

## Test locations

| Area | Source |
|---|---|
| Backend | `backend/tests/test_*.py` |
| Frontend assertions | `frontend/src/**/*.test.ts` and `*.test.tsx` |
| Desktop and storage lifecycle | `desktop/tests/*.test.cjs` |
| Docker runtime acceptance | `backend/tests/test_docker_runtime_security.py` |
| Packaged clean-machine acceptance | `desktop/scripts/clean-machine-acceptance.ps1` |

Generated frontend files under `frontend/.tmp-tests` are test-runner output,
not the source of test behavior.

## Durable coverage areas

### API and response contracts

Backend API tests cover:

- health, releases, issues, sprints, metrics, signals, sync, configuration,
  administration, reports, and metric metadata;
- pagination, filtering, path/query validation, missing entities, and
  structured empty responses;
- partial, inconclusive, not-computed, and legacy ruleset behavior;
- release and sprint response-assembly services independently from thin routes;
- snapshot comparisons, history, version boundaries, provenance, and stored
  evidence;
- the registered route-security inventory and deployment-aware bearer
  authentication;
- README endpoint inventory, current migration head, canonical terminology,
  and other documentation contracts.

### Deterministic metrics and signals

Service tests cover:

- release metrics, sprint metrics, flow evaluators, current-scope semantics,
  sprint work-state classification, and workload distribution;
- exact threshold boundaries, empty denominators, missing classifications,
  incomplete changelog history, repeated reopen events, and story-point
  coverage;
- sprint delivery-confidence prerequisites, components, partial and
  inconclusive states, and deterministic explanations;
- release signal hard rules, confidence bands, gates, Release Outlook, risk
  aging, and 24-hour evidence;
- confidence breakdowns, biggest drivers, recommendations, and snapshot delta
  contributors;
- ruleset immutability and cross-version comparison safeguards.

### Metric catalog and presentation drift

Catalog tests verify:

- exactly one definition for every release and sprint API metric;
- immutable metadata, deterministic order, thresholds, availability
  dependencies, and feature participation;
- exact public metadata and OpenAPI serialization;
- threshold consumers remain synchronized with the catalog;
- the generated frontend fallback is byte-equivalent to the backend export;
- frontend runtime compatibility checks and fallback behavior;
- frontend and report labels, units, formatting, and precision remain aligned.

### Jira ingestion, configuration, and privacy

Tests cover Jira request normalization and error mapping, field mappings,
paginated ingestion, idempotent upserts, release and sprint membership,
changelog completeness, downstream recomputation, and controlled sync
failures. Configuration and privacy coverage includes:

- deployment-specific startup validation;
- direct and file-based secret-source conflicts;
- non-Electron credential-write rejection and desktop token handling;
- atomic nonsecret configuration updates;
- error, response, and log redaction.

All Jira network behavior in the normal backend suite uses fakes or mocked
transport. Real Jira credentials are not required for automated unit and
integration tests.

### Database, migrations, and startup

Database tests cover:

- the complete Alembic graph and single-head requirement;
- fresh, versioned, and explicitly recognized unversioned SQLite sources;
- every supported prior revision upgrading to the current head;
- representative data preservation and idempotent restart;
- fail-closed SQLite migration-backup creation, validation, publication, and
  reuse;
- application startup readiness through the real backend entry point;
- SQLite and PostgreSQL schema parity at the migration boundary.

Most backend tests use isolated SQLite databases. PostgreSQL-marked tests are a
separate acceptance layer and require an explicit disposable admin target.

### Reporting

Reporting tests exercise prepared data, immutable document models, focused
release/sprint/overview/documentation templates, chart rendering, PDF byte
generation, response headers, missing entities, partial evidence, stored
rulesets, and presentation synchronization with the metric catalog.

### Frontend

Frontend assertion files cover authentication helpers, workspace and release
selection, navigation, Jira configuration payloads, metric availability,
sprint delivery confidence, charts, recommendations, catalog compatibility,
and workspace hooks. `npm test` compiles and runs these deterministic Node
assertions; it is not a browser end-to-end suite.

`npm run build` is a separate required check. It performs TypeScript project
compilation and a production Vite build, catching integration and bundling
problems that assertion tests do not.

### Desktop and storage lifecycle

Desktop Node tests cover Electron startup and security contracts, backend
process control, operation locking, transactional backup/restore, Clear Data,
Factory Reset, rollback, interrupted-journal recovery, and release/acceptance
script contracts. These tests use Node's built-in test runner and do not launch
the Electron GUI.

Packaged acceptance is separate. It verifies the real embedded backend,
frontend assets, Electron application, installer artifacts, local persistence,
upgrade behavior, native PDF save flow, and operation recovery boundaries.

## Local prerequisites

Install backend and development dependencies in a virtual environment:

```bash
cd backend
python -m pip install -e .
python -m pip install -r requirements-dev.txt
```

Install frontend and desktop dependencies in each package:

```bash
cd frontend
npm install

cd ../desktop
npm install
```

Use Python 3.11 or newer and a supported Node.js/npm installation. Normal
backend tests do not require Jira, Docker, PostgreSQL, or Electron.

## Focused verification

Run the smallest relevant test module while developing:

```bash
cd backend
python -m pytest tests/test_metric_catalog.py -q
python -m pytest tests/test_metrics_api.py tests/test_sprints_api.py -q
python -m pytest tests/test_reporting_api.py -q
```

Pytest expressions are useful when iterating on one behavior:

```bash
python -m pytest tests/test_analytics_service.py -k reopen -q
```

Frontend and desktop focused commands are package-level because their runners
already execute small deterministic suites:

```bash
cd frontend
npm test

cd ../desktop
npm test
```

## Full repository verification

Run all normal backend tests and lint:

```bash
cd backend
python -m pytest tests -q
python -m ruff check app tests alembic
```

Run frontend assertions and the production build:

```bash
cd frontend
npm test
npm run build
```

Run desktop syntax and lifecycle tests:

```bash
cd desktop
npm test
```

These commands are the normal cross-platform regression checks. Environment-
marked PostgreSQL and Docker tests may skip when their explicit prerequisites
are absent.

## PostgreSQL acceptance

PostgreSQL migration and application-startup acceptance requires a real
PostgreSQL admin URL capable of creating and dropping disposable databases.
The tests create only names beginning with `lighthouse_migration_` and refuse
to drop anything outside that namespace.

Set `MIGRATION_TEST_POSTGRES_ADMIN_URL` and run:

```bash
cd backend
MIGRATION_TEST_POSTGRES_ADMIN_URL=postgresql+psycopg://postgres:<password>@127.0.0.1:5432/postgres \
  python -m pytest \
    tests/test_migration_upgrade_matrix.py \
    tests/test_application_startup_acceptance.py \
    -m postgres -q
```

When using the repository's Docker Compose database, first configure the
required synthetic secret files and start PostgreSQL with the loopback-only
`docker-compose.postgres-local.yml` override described in `README.md`. The base
Compose configuration intentionally does not publish PostgreSQL to the host.
Never point this variable at the normal LighthousePM application database.

## Docker security acceptance

The Docker acceptance test builds an isolated Compose project with synthetic
API and PostgreSQL secrets, chooses a free loopback backend port, verifies
authentication and configuration-write behavior, and removes its containers,
volumes, and local images afterward.

Prerequisites:

- Docker CLI with Compose;
- a reachable Docker daemon;
- permission and resources to build and run the backend and PostgreSQL images;
- no real LighthousePM or Jira credentials.

Require the test instead of allowing a skip:

```bash
cd backend
LIGHTHOUSE_REQUIRE_DOCKER_SECURITY=1 \
  python -m pytest tests/test_docker_runtime_security.py -m docker -q
```

## Security acceptance gate

The desktop package provides the combined automated gate:

```bash
cd desktop
npm run verify:security
```

It runs the full backend tests and lint, frontend assertions and production
build, and desktop tests. It finds Python through `LIGHTHOUSE_PYTHON`, the
repository virtual environment, or a supported system interpreter.

If Docker is available, the gate requires the isolated Docker security test.
In CI or another environment where Docker coverage is mandatory, set
`LIGHTHOUSE_REQUIRE_DOCKER_SECURITY=1`; the gate then fails instead of skipping
when Docker is unavailable.

## Electron packaging and release verification

Packaging requires:

- Windows when producing and validating the supported Windows distributables;
- frontend and desktop npm dependencies;
- the project Python environment with PyInstaller from
  `backend/requirements-dev.txt`;
- sufficient disk space for the embedded Python backend, Electron package,
  Squirrel installer, and ZIP artifact.

Useful commands:

```bash
cd desktop
npm run package
npm run make
npm run verify:release
```

`npm run package` creates the unpacked Electron application. `npm run make`
also creates the Windows installer and ZIP. `npm run verify:release` validates
the expected existing artifacts; it does not build them. Set
`REQUIRE_WINDOWS_CODE_SIGNING=1` to make valid Authenticode signatures
mandatory during artifact verification.

The complete Windows release command is:

```bash
cd desktop
npm run release:windows
```

It runs the security gate before building and verifying release artifacts.

## Clean-machine packaged acceptance

Automated source tests do not replace clean-machine acceptance. Run the
packaged installer on a Windows test machine or VM that does not have Python,
Node.js, PostgreSQL, or Docker installed:

```powershell
cd desktop
npm run acceptance:clean-machine -- -RequireNoDevTools
```

This acceptance is interactive and requires deliberately supplied Jira test
credentials and a project with representative release and sprint data. It
checks installation, startup, sync, offline restart, PDF export, version-2
Settings Backup and Restore, Clear Data, Factory Reset, and retained local
state. Upgrade approval additionally requires a previous installer:

```powershell
npm run acceptance:clean-machine -- `
  -RequireNoDevTools `
  -PreviousSetupPath C:\path\to\previous\LighthousePM-Setup.exe
```

Clean-install and upgrade runs must use uncontaminated user-data state and
produce separate approved reports under `desktop/out/acceptance`. Follow the
full evidence and cleanup procedure in `desktop/README.md`.

## Definition of done

A change is verified only when:

- focused tests cover the changed boundaries and edge cases;
- the normal backend, frontend, and desktop regression commands pass;
- required environment-specific acceptance layers run instead of silently
  skipping;
- generated catalog and endpoint/documentation drift checks pass;
- packaging and clean-machine evidence is refreshed when release artifacts or
  desktop lifecycle behavior changes.
