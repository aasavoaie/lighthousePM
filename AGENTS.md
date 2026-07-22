# AGENTS

Guidelines for AI agents working in this repository.

## Goal

Build and maintain a product that:

- ingests Jira data;
- computes deterministic, reproducible metrics;
- produces explainable release-risk signals;
- exposes stable, structured APIs and reports; and
- supports the desktop, local-browser, and Docker deployment modes documented by the project.

## Sources of truth

- `PRODUCT_RULES.md` is the normative authority for product behavior, metric formulas, thresholds, availability, evidence, and user-visible terminology.
- `backend/app/metric_catalog.py` is the machine-readable implementation authority for current metric metadata. It must describe approved product rules; it must not invent them.
- OpenAPI is the API contract. `README.md`, `HELPER.md`, `UNIT_TEST_DOCS.md`, and `ABOUT.md` explain setup, operation, tests, and product behavior without overriding the product rules.
- When these sources disagree, stop and reconcile the product rule first. Do not silently choose a convenient interpretation.

## Core principles

### Deterministic first

- Compute outputs explicitly. Do not add inference, guess-based logic, or hidden behavior.
- Keep formulas, thresholds, rounding, availability, and evidence rules visible and testable.
- Preserve the provenance and ruleset needed to reproduce stored results.

### Simplicity over architecture

- Keep the current single-service architecture.
- Do not introduce microservices, a generic abstraction framework, or unnecessary layers.
- Add a boundary only when it gives an existing responsibility a clear home.

### Clarity over cleverness

- Prefer small functions, type hints, explicit control flow, and focused modules.
- Keep code easy to read, debug, and audit.
- Avoid deep inheritance and premature optimization.

### Trust is critical

- Every signal must include explicit reasons.
- Every metric must be reproducible from its defined inputs.
- Partial, unavailable, inconclusive, legacy, and degraded states must be represented honestly rather than hidden or estimated.

## Backend boundaries

FastAPI provides the API and PostgreSQL provides persistent storage. Business behavior belongs in focused services:

| Area | Responsibility |
| --- | --- |
| `jira_service.py` | Jira API access and normalized external responses |
| `sync_service.py` | Ingestion orchestration and persisted Jira data |
| `analytics_service.py` | Deterministic metric formulas |
| `signal_service.py` | Rule-based risk signals and reasons |
| `metric_recompute_service.py` | Mutating metric recomputation and its transaction boundary |
| `release_metrics_response_service.py` | Release metric response assembly |
| `sprint_response_service.py` | Sprint list, detail, history, and comparison response assembly |
| `metric_availability_service.py` | Runtime metric availability and coverage states |
| `metric_catalog_service.py` | Public catalog selection and serialization |

API routes are thin controllers. They may validate requests, resolve dependencies, call one application service, and translate known application errors to HTTP responses. They must not contain formulas, response assembly, transaction orchestration, report construction, or duplicated authorization policy.

Response-assembly services coordinate reads and construct API schemas. They must preserve stored artifact provenance, ruleset versions, legacy behavior, availability, and evidence. They do not redefine formulas or current catalog semantics, and read-only assembly must not commit database transactions.

Mutation services own writes and transaction boundaries. A multi-step mutation must succeed or fail atomically unless an approved product rule explicitly says otherwise.

## Metrics and signals

- Metrics must be deterministic, testable, documented, and consistent with `PRODUCT_RULES.md`.
- Thresholds and assumptions must never be implicit.
- Metric availability is separate from metric value. Do not turn missing or insufficient data into a reassuring value.
- Signals must be rule-based, persisted where required by the product rules, and include structured reasons and supporting evidence.
- Historical results retain their original ruleset and provenance. Do not reinterpret stored history with the current catalog.

## Metric catalog boundary

The metric catalog owns mechanical metadata such as stable keys, labels, descriptions, units, formats, display order, thresholds, availability descriptions, evidence references, API fields, history participation, and ruleset metadata.

It does not own formulas, signal evaluation, runtime availability decisions, database queries, or response orchestration. Those remain in their focused services.

Backend API metadata and frontend display metadata must come from the catalog. The frontend's generated fallback is produced with `backend/scripts/export_metric_catalog.py`; do not hand-edit `frontend/src/generated/metricCatalogFallback.json`.

For a metric behavior change:

1. discuss and approve the product rule;
2. update `PRODUCT_RULES.md`;
3. update the catalog and focused implementation;
4. increment the ruleset when behavior or interpretation changes; and
5. add contract, drift, boundary, and edge-case tests as appropriate.

## Reporting boundary

Reporting remains part of the single backend service and is split by concrete responsibility:

| Module | Responsibility |
| --- | --- |
| `report_document_models.py` | Stable report document structures |
| `report_data_preparation.py` | Preparing report data from stored artifacts |
| `report_*_template.py` | Focused report sections and templates |
| `report_chart_renderer.py` | Chart rendering |
| `report_pdf_renderer.py` | PDF rendering |
| `report_theme.py` | Shared report presentation constants |
| `reporting_service.py` | Small application facade coordinating the reporting pipeline |

Reports consume stored metric artifacts, evidence, provenance, and the applicable ruleset. They must not recompute metrics independently, reinterpret historical data with current rules, or create a second metric-label and formatting system.

## Frontend boundaries

- `frontend/src/App.tsx` is the application shell. It owns authentication, top-level navigation, active project/release context, and page selection.
- Page/container modules own data fetching, cancellation, stale-response protection, loading, and error state.
- Presentational components receive data and callbacks; they do not call the API or duplicate metric rules.
- Sprint UI keeps one data-owning container and focused presentational sections for selection, summary, health, ticket situations, delivery confidence, metrics, evidence, charts, history, comparison, and reporting.
- Intelligence and reporting views share established data ownership rather than issuing duplicate requests.
- Pure metric evaluation and formatting helpers stay separate and directly testable.
- Use catalog metadata for metric labels, descriptions, units, order, precision, thresholds, and availability guidance. Use the generated fallback only when live metadata is unavailable or incompatible.
- Do not add a router, global state framework, generic component framework, or other architectural layer without an approved need.

## API and security rules

- Use RESTful endpoints, structured JSON responses, and consistent naming.
- Keep the OpenAPI schema accurate and cover important contracts with tests.
- Apply the deployment-mode authentication and binding rules defined in `PRODUCT_RULES.md`.
- Protect mutating and administrative operations with the central capability policy. Do not duplicate endpoint security inventories in feature code.
- Never log or expose API tokens, Jira credentials, database passwords, or other secrets.
- Persist credentials only through the approved secure mechanism for the active deployment mode.

## Testing

Focus on metric correctness, signal logic, response contracts, provenance, security boundaries, and report consistency. Include:

- empty datasets and missing optional data;
- exact threshold boundaries and rounding;
- partial, inconclusive, unavailable, legacy, and degraded states;
- transaction rollback and idempotency for mutations;
- API authentication and configuration-write behavior by deployment mode;
- catalog inventory, serialization, generated-fallback, and consumer drift;
- frontend loading, error, stale-response, and fallback behavior; and
- report data, formatting, charts, templates, and PDF smoke coverage.

Run focused tests after each approved implementation point, then run the relevant full backend, frontend, desktop, migration, or packaging checks before declaring the phase complete. Follow `UNIT_TEST_DOCS.md` for supported commands and prerequisites.

## Do not

- add guess-based metrics or undocumented thresholds;
- mix business logic into API routes or React presentational components;
- recompute the same metric independently in API, frontend, and reporting code;
- introduce microservices or unnecessary generic abstractions;
- change generated catalog artifacts by hand;
- overwrite unrelated work in a dirty worktree; or
- claim a check passed when its prerequisites were unavailable.

## Definition of done

A task is complete when:

- the approved product rule and implementation agree;
- logic is deterministic and results are reproducible;
- responsibilities remain in the boundaries above;
- APIs and user-visible states are structured, stable, and explainable;
- relevant tests pass, including boundaries and edge cases; and
- documentation and generated artifacts are synchronized.
