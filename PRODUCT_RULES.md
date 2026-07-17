# LighthousePM Product Rules

## Purpose

This document is the canonical catalog for LighthousePM metric, confidence,
signal, and availability rules. It exists to make every leadership-facing
output explicit, deterministic, testable, and reproducible, as required by
`AGENTS.md`.

This catalog describes the current implementation and identifies rules that
still require an explicit product decision. A rule marked **Pending decision**
is not approved merely because the current code implements it.

## Rule Status

- **Approved:** the rule is an accepted product contract.
- **Current behavior:** the rule is implemented and documented here, but has
  not yet been approved as the long-term product contract.
- **Pending decision:** the current behavior is disputed, incomplete, or
  inconsistent with another documented rule. The related Phase 0 decision
  must be completed before behavioral changes are implemented.

## Required Rule Definition

Every metric or derived signal must define:

1. Public name and API field name.
2. Scope: release, sprint, project, or system.
3. Source records and required Jira fields.
4. Formula, unit, denominator, and time window.
5. Boundary behavior and rounding.
6. Missing, partial, and empty-data behavior.
7. Stored evidence required to reproduce the result.
8. Thresholds and their decision meaning.
9. Implementing service and focused tests.
10. Rule version once rule versioning is approved.

## Shared Classification Rules

Status: **Current behavior**

| Classification | Current values |
|---|---|
| Done statuses | `done`, `closed`, `resolved` |
| In-progress statuses | `in progress`, `in development`, `in review`, `in testing` |
| High-severity values | `high`, `highest`, `critical` |
| Bug identification | `issue_type`, case-insensitively equal to `bug` |

All comparisons are case-insensitive. Jira field identifiers can be configured,
but the classification values above are currently code constants. Projects
using other workflow or priority names will produce incomplete results until
these mappings become explicit configuration.

## Jira Time Fields

Status: **Approved — Phase 0.4**

- `jira_created_at` is the issue creation timestamp returned by Jira.
- `jira_updated_at` is the latest issue update timestamp returned by Jira.
- Both values are persisted separately from local database `created_at` and
  `updated_at` audit timestamps.
- Jira timestamps are normalized to UTC without changing the represented
  instant.
- Local insertion or update time must never substitute for a missing Jira time
  in a product metric.
- When a required Jira timestamp is unavailable, the affected metric is
  unavailable or partial with an explicit reason.

## Release Metrics

### Open blockers (`open_blockers`)

Status: **Current behavior**

- Scope: issues currently associated with the release.
- Formula: count issues where `is_blocker = true` and status is not done.
- Unit: tickets.
- Evidence: sorted matching Jira issue keys are stored on the metric snapshot.
- Empty scope: stored computation is `0`; API availability identifies the
  release as not computed when it has no tickets.

### Open high-severity bugs (`open_high_severity_bugs`)

Status: **Current behavior**

- Scope: issues currently associated with the release.
- Formula: count issues whose type is Bug, severity is a configured
  high-severity value, and status is not done.
- Unit: tickets.
- Evidence: sorted matching Jira issue keys are stored on the metric snapshot.

### Scope completed (`scope_completed_pct`)

Status: **Current behavior**

- Formula: `100 * current done release tickets / current release tickets`.
- Unit: percent from `0` to `100`.
- Rounding: two decimal places.
- Empty scope: `0.0`, with API availability marking the metric unavailable.
- Story points are not used.

### Completed tickets (`completed_tickets`)

Status: **Current behavior**

- Formula: count current release tickets whose status is done.
- Unit: tickets.

### Scope churn, added scope, and removed scope

Fields: `scope_churn_7d_pct`, `scope_added_7d_count`,
`scope_removed_7d_count`

Status: **Current behavior**

- Window: the seven days before recomputation time.
- Source: fix-version changelog records in the configured Jira project where
  the old or new value exactly matches the release name, case-insensitively.
- Churned scope: distinct Jira issue keys with at least one matching change.
- Added scope: distinct keys moving from outside the release into the release.
- Removed scope: distinct keys moving from the release to outside the release.
- Churn formula:
  `100 * distinct churned issue keys / current release ticket count`.
- Rounding: two decimal places.
- Empty current scope: all three values are `0`.

The percentage can exceed `100` when removed or repeatedly moved issues exceed
the current release ticket count. Whether the denominator should instead be
initial or union scope remains a future product decision.

### Median cycle time (`median_cycle_time_days`)

Status: **Current behavior**

- Scope: currently done release tickets.
- Start: earliest transition into an in-progress status.
- End: earliest transition into a done status.
- Tickets missing either transition, or whose start is not before the end, are
  excluded.
- Formula: statistical median of included elapsed durations.
- Unit: days.
- Rounding: four decimal places.
- No qualifying tickets: `null`.

### Reopen rate (`reopen_rate_pct`)

Status: **Current behavior**

- Reopened ticket: a current release ticket with at least one transition from
  a done status to a non-done status.
- Formula: `100 * distinct reopened ticket keys / current release ticket count`.
- Unit: percent from `0` to `100`.
- Rounding: two decimal places.
- Empty scope: `0.0`, with API availability marking the metric unavailable.

## Release Confidence and Readiness

Status: **Approved — Phase 0.2**

Release confidence and release signal severity are related but distinct:

- The confidence score measures accumulated risk using weighted risk points.
- Hard rules set the minimum signal severity for individually significant
  conditions.
- The final release signal is the more severe result from the hard rules and
  the confidence-score band.

### Confidence risk points

| Condition | Risk points |
|---|---:|
| Open blockers greater than `0` | 28 |
| Open high-severity bugs greater than `1` | 18 |
| Open high-severity bugs greater than `0`, otherwise | 9 |
| Scope churn greater than `20%` | 8 |
| Scope churn greater than `10%`, otherwise | 4 |
| Reopen rate greater than `15%` | 6 |
| Reopen rate greater than `10%`, otherwise | 3 |
| Median cycle time greater than `7` days | 4 |

Confidence formula:

`max(0, 100 - sum(active risk points))`, rounded to one decimal place.

Confidence-score severity bands:

- RED: confidence less than or equal to `60`.
- YELLOW: confidence greater than `60` and less than or equal to `90`.
- GREEN: confidence greater than `90`.

### Hard-rule severity

Hard RED conditions:

- Open blockers greater than `0`.
- Open high-severity bugs greater than `1`.
- Scope churn greater than `20%`.
- Reopen rate greater than `15%`.

Hard YELLOW conditions, when no hard RED condition is active:

- Open high-severity bugs greater than `0`.
- Scope churn greater than `10%`.
- Reopen rate greater than `10%`.
- Median cycle time greater than `7` days.

Hard-rule severity is GREEN when none of these conditions is active. All
comparisons are strict `>` comparisons, so a value exactly equal to a threshold
does not breach that threshold.

### Final signal

Severity order is `GREEN < YELLOW < RED`.

`final signal = max(hard-rule severity, confidence-score severity)`.

Consequences:

- An individually critical metric can never be hidden by a high confidence
  score.
- Multiple moderate risks can escalate to RED through their accumulated
  confidence impact.
- A lower-severity confidence band can never downgrade a hard-rule result.

The signal response must include every active breached rule as an explicit,
machine-readable reason with metric name, observed value, comparison,
threshold, and severity. Human-readable reasons must be generated from the
same structured rules. Ordering must be deterministic: severity first, then
the stable product-rule order shown above.

### Release readiness

Release readiness uses five pass/fail gates:

1. Open blockers `<= 0`.
2. Open high-severity bugs `<= 1`.
3. Scope churn `<= 20%`.
4. Reopen rate `<= 15%`.
5. Median cycle time is unavailable or `<= 7` days.

`readiness_pct = 100 * passed gates / total gates`.

## Sprint Metrics

### Committed scope (`committed_scope`)

Status: **Current behavior**

- Formula: count current issue-to-sprint membership records.
- Unit: tickets.
- This is current membership, not necessarily the sprint-start commitment.

### Completed scope (`completed_scope_pct`)

Status: **Current behavior**

- Formula: `100 * current done sprint tickets / current sprint tickets`.
- Unit: percent from `0` to `100`.
- Rounding: two decimal places.
- Empty scope: `0.0`, with API availability marking the metric unavailable.

### Sprint blockers and high-severity bugs

Fields: `open_blockers`, `open_high_severity_bugs`

Status: **Current behavior**

- These use the same classification rules as their release equivalents.
- Scope is current issue-to-sprint membership.
- Sorted matching issue keys are stored on the sprint metric snapshot.

### Bugs created during sprint (`bugs_created_during_sprint`)

Status: **Approved — Phase 0.4**

- Count Bug tickets linked to the sprint whose `jira_created_at` is between the
  sprint start and effective sprint end, inclusively.
- For a closed sprint, effective end is completion time when present, otherwise
  configured end time, otherwise snapshot time.
- For an active or other non-closed sprint, effective end is the earlier of
  configured end time and snapshot time, or snapshot time when no end exists.
- If sprint start is missing, the metric is unavailable.
- Tickets missing `jira_created_at` are not silently counted or discarded: the
  metric is marked partial and exposes their sorted Jira keys.
- Local database insertion time is never used by this metric.

### Work-state counts

Fields: `in_progress_count`, `not_started_count`, `rollover_count`

Status: **Current behavior**

- In progress: current sprint tickets in an in-progress status.
- Not started: current sprint tickets in neither a done nor in-progress status.
- Rollover: for a closed sprint, current sprint tickets not currently done;
  otherwise `0`.

### Sprint median cycle time and reopen rate

Fields: `median_cycle_time_days`, `reopen_rate_pct`

Status: **Current behavior**

- These use the same formulas as the release equivalents, scoped to current
  sprint membership.

## Sprint Delivery Confidence

Status: **Approved — Phase 0.3**

LighthousePM calculates delivery confidence only when at least `50%` of the
current sprint tickets have valid story points. Missing values are never
imputed or replaced with an invented point value.

### Story-point coverage

Coverage formula:

`100 * tickets with valid story points / total current sprint tickets`.

- A non-negative numeric value, including zero, is a valid story-point value.
- A missing, null, non-numeric, or negative value is unpointed.
- Coverage is rounded to two decimal places.
- Evidence includes total, pointed, and unpointed ticket counts, coverage
  percentage, and sorted unpointed Jira ticket keys.

### Empty sprint

When the sprint contains no tickets:

- `delivery_confidence` is `null`.
- Delivery-confidence status is `NOT_COMPUTED`.
- The explanation states that the sprint has no tickets to evaluate.

### Inconclusive coverage

When no sprint tickets have story points, or coverage is below `50%`:

- `delivery_confidence` is `null`.
- The response marks delivery confidence as `INCONCLUSIVE`.
- Ticket-based metrics remain available when they are not calculated from
  aggregated story points.
- Velocity, workload distribution, and other aggregated story-point outputs
  are unavailable.
- The explanation states:

> Delivery confidence is inconclusive because fewer than 50% of the sprint
> tickets have story points. At least 50% of the tickets inside the sprint must
> have story points to calculate delivery confidence. Ideally, all tickets
> should have story points.

### Partial coverage

When coverage is at least `50%` but below `100%`:

- Delivery confidence is calculated and returned.
- The response marks delivery confidence as `PARTIAL`.
- Point-based components use only tickets with valid story points.
- Blocker health, scope stability, and ticket-count metrics use the complete
  sprint scope.
- No default story-point value is assigned to unpointed tickets.
- Point-based cards and recommendations display the same partial-data state.
- The explanation states:

> Delivery confidence is partial because X of Y sprint tickets have story
> points. Point-based calculations use tickets with available story points,
> while blocker and scope calculations use the complete sprint scope.

- A second sentence states:

> When all sprint tickets have story points, delivery confidence uses the
> complete sprint scope and returns the accurate value for the documented
> model. The PARTIAL label and these remarks are then removed.

The score must not be described as fully representative while coverage is
partial.

### Complete coverage

When coverage is `100%`:

- Delivery confidence is calculated from the complete sprint scope.
- Delivery-confidence status is `COMPUTED`.
- Current-sprint partial-coverage explanations are removed.
- Point-based cards and recommendations are presented normally.

### Effective-point values

- Committed points: sum of non-negative story points across current sprint
  tickets included in the point-based calculation.
- Completed points: sum of those points for currently done tickets.
- Remaining points: `max(committed - completed, 0)`.

### Component rules

#### Progress alignment

- Point completion: `100 * completed points / committed points`.
- If committed points are zero, completion is `100`.
- Time elapsed: clamped percent of sprint duration elapsed at snapshot time.
- Component: `clamp(100 * point completion / time elapsed, 0, 100)`.
- If elapsed time is unavailable or zero, component is `100`.

#### Velocity fit

- Baseline: up to the three most recent closed sprints in the same project that
  ended no later than the target sprint start/reference date and have at least
  `50%` story-point coverage.
- A partially pointed baseline sprint contributes only its pointed tickets.
- Each baseline sprint's story-point coverage is stored and exposed.
- Historical velocity: average completed points across the baseline.
- Remaining time ratio: `clamp((100 - elapsed percent) / 100, 0, 1)`.
- Remaining capacity: `historical velocity * remaining time ratio`.
- Component is `100` when no work remains, `50` when no baseline exists, `0`
  when remaining capacity is zero, otherwise
  `clamp(100 * remaining capacity / remaining points, 0, 100)`.
- If no eligible baseline exists, the neutral fallback is used and the response
  explains that historical velocity is unavailable.
- Velocity-based output is marked `PARTIAL` when any contributing baseline
  sprint has partial coverage, even if current-sprint coverage is complete.

#### Blocker health

- Blocked ratio: `open blockers / committed ticket count`, or `0` for empty scope.
- Component: `clamp(100 * (1 - blocked ratio), 0, 100)`.

#### Scope stability

- Post-start additions and removals are reconstructed from sprint changelog.
- Initial commitment count:
  `max(current ticket count - added count + removed count, 0)`.
- Stability index:
  `(added count + removed count) / initial commitment count`.
- Component: `clamp(100 * (1 - stability index), 0, 100)`.
- A missing stability index is currently treated as zero churn.

Delivery confidence formula:

`0.40 * progress alignment + 0.30 * velocity fit + 0.20 * blocker health + 0.10 * scope stability`.

### Ticket-based metrics during incomplete coverage

The following remain available because they are not calculated from aggregated
story points:

- committed ticket count and completed ticket percentage;
- open blockers and open high-severity bugs;
- bugs created during the sprint;
- in-progress, not-started, and rollover counts;
- median cycle time and reopen rate; and
- ticket-based scope movement and stability evidence.

### Workload distribution

- Below `50%` current-sprint coverage, workload distribution is
  `INCONCLUSIVE`.
- From `50%` up to but not including `100%`, workload distribution uses pointed
  active tickets, excludes unpointed active tickets, reports how many were
  excluded, and is marked `PARTIAL`.
- At `100%`, it uses the complete active sprint scope and is `COMPUTED`.

### Persistence and API evidence

Sprint snapshots must store:

- total, pointed, and unpointed current-sprint ticket counts;
- story-point coverage percentage and sorted unpointed ticket keys;
- delivery-confidence status: `NOT_COMPUTED`, `INCONCLUSIVE`, `PARTIAL`, or
  `COMPUTED`;
- the score when calculated;
- component values and calculation inputs; and
- historical baseline identifiers and coverage details.

This evidence must be returned by the API so every score and unavailable state
remains explainable and reproducible.

## Metric Availability

Status: **Approved for story-point behavior — Phase 0.3**

- No scoped tickets: computation status is `NOT_COMPUTED`.
- Tickets exist but no snapshot exists: `NOT_COMPUTED`.
- Snapshot exists but one or more metric dependencies are missing: `PARTIAL`.
- All dependencies exist: `COMPUTED`.
- Changelog-based metrics require at least one stored changelog entry in scope.
- Sprint delivery-confidence availability and status follow the story-point
  coverage rules above. The delivery-confidence status does not suppress
  otherwise available ticket-based metrics.
- Median cycle time availability currently requires at least one completed
  ticket and at least one changelog entry; the computed value can still be
  `null` when no valid transition pair exists.

APIs must expose unavailable values explicitly and must not replace unknown or
unavailable values with inferred healthy values.

## Risk Aging

Status: **Approved — Phase 0.4**

LighthousePM exposes issue age and risk age as separate facts.

### Issue age

- Meaning: elapsed time from `jira_created_at` to the stored snapshot time.
- Formula: `max(0, snapshot time - jira_created_at)` in days.
- Rounding: one decimal place.
- Missing Jira creation time: `null` with an explicit unavailable reason.

Issue age provides context but is not the primary leadership risk-aging value.

### Risk age

- Meaning: elapsed time since the current uninterrupted risk condition became
  active.
- Formula: `max(0, snapshot time - risk_started_at)` in days.
- Rounding: one decimal place.
- The leadership risk-aging cards use risk age, not issue age.

A blocker risk is active when the normalized blocker classification is true
and the issue is not done. A high-severity-bug risk is active when the issue is
a Bug, its configured severity is high, and it is not done.

`risk_started_at` is the latest proven transition from an inactive state to the
currently active risk state. The derivation uses the complete relevant Jira
history for:

- status;
- severity/priority;
- issue type;
- the configured blocker field; and
- any other configured field used by blocker classification.

If a risk is active from issue creation and complete relevant history proves
there was no later reactivation, `risk_started_at` is `jira_created_at`.

When a risk is resolved or otherwise becomes inactive, its uninterrupted age
ends. If it becomes active again, risk age restarts from the new activation
time.

### Incomplete evidence

- Changelog ingestion must record whether all history required for the risk
  derivation was fetched successfully.
- If the activation time cannot be proven, `risk_started_at` and `risk_age`
  are `null` with reason `Risk start unavailable from Jira history.`
- Local database insertion time must never be used as a fallback.
- An active risk remains included in the active-risk count even when its age is
  unavailable.
- Aggregates expose total active count, known-age count, and unknown-age count.
- Oldest and average age use only known ages and are marked partial whenever
  unknown ages exist.

### Stored evidence

For every active aged risk, the stored evidence includes:

- Jira issue key and risk type;
- Jira issue creation time;
- risk start time and the source field/change when known;
- snapshot time used as the calculation boundary;
- issue age and risk age;
- history-completeness status; and
- unavailable reason when the risk start is unknown.

The API and reports expose the same evidence and never infer a healthy age from
missing data.

## Release Outlook

Status: **Approved — Phase 0.5**

Release Outlook summarizes current release evidence. It is not a forecast and
must not claim a probability, likelihood, predicted future confidence, or
chance of meeting release targets.

The previous frontend calculation that extrapolated confidence and multiplied
it by readiness percentage is not an approved product rule and must be removed
when this contract is implemented.

### Outlook evidence

Release Outlook displays only deterministic evidence from stored data:

- current confidence score and final release signal;
- passed and failed release gates;
- confidence change over the latest 24-hour baseline when one exists;
- signed calendar days remaining until the Jira release date; and
- every active hard RED and YELLOW condition.

Days remaining is the Jira release calendar date minus the UTC calendar date of
the latest snapshot:

- positive: release date is in the future;
- zero: release date is today;
- negative: release date has passed; and
- `null`: Jira release date or latest snapshot is unavailable.

The 24-hour confidence change compares the latest snapshot with the latest
snapshot at or before `latest snapshot time - 24 hours`. If no such baseline
exists, the change is unavailable and is not inferred from a newer point.

### Outlook label

The label maps directly from the approved final release signal:

| Final signal | Outlook label |
|---|---|
| GREEN | `ON TRACK` |
| YELLOW | `NEEDS ATTENTION` |
| RED | `AT RISK` |
| Not computed | `NOT COMPUTED` |

The UI and reports state: `This outlook reflects the latest stored snapshot and
is not a forecast.`

### Future forecasting

Any future forecast is a separate versioned product feature. Before release it
requires an approved formula, minimum-history and data-quality rules,
validation against historical outcomes, explicit uncertainty, reproducible
stored inputs, and wording that does not present an uncalibrated score as a
probability.

## Reproducibility and Rule Versioning

Status: **Approved — Phase 0.6**

### Version format

- LighthousePM uses one monotonically increasing integer `ruleset_version` for
  release and sprint product rules.
- Version `0` identifies existing legacy results created without an explicit
  ruleset version.
- Version `1` identifies the approved Phase 0 contract once that contract is
  implemented in runtime code.
- The version increments whenever a formula, threshold, weight,
  classification, availability rule, or output meaning changes.
- Wording, layout, and other presentation-only changes do not increment the
  version when they leave calculated behavior and output meaning unchanged.

### Snapshot provenance

Every release and sprint metric snapshot stores:

- `ruleset_version`;
- calculated confidence score and status when applicable;
- thresholds and weights used;
- classification and relevant per-project configuration values;
- availability, story-point coverage, and history-completeness evidence;
- component inputs and outputs;
- source snapshot/calculation time; and
- the issue-key evidence required by the calculated metrics.

Stored results are immutable. Recomputing metrics creates a new snapshot and
does not update an earlier snapshot in place.

### Release signal history

Release signals are append-only historical results rather than one mutable row
per release.

Each signal record stores:

- release and metric-snapshot identifiers;
- `ruleset_version`;
- final signal and confidence score;
- structured and human-readable reasons;
- release gates and readiness evidence;
- risk-aging evidence; and
- calculation time.

At most one signal result may exist for the same release, metric snapshot, and
ruleset version. A later recomputation creates a new metric snapshot and signal
record. It never rewrites the older signal.

### Historical behavior

- Historical derived results are read from stored values and are never
  recalculated with the current ruleset.
- A ruleset change does not rewrite or mass-convert old snapshots.
- API responses and PDF reports expose `ruleset_version` for every derived
  result.
- Charts expose the ruleset version for each point and visibly mark version
  boundaries.
- Deltas and driver comparisons between different ruleset versions are
  unavailable with an explicit version-mismatch reason.
- A new snapshot under the current ruleset starts a new comparable trend
  segment.

### Legacy results

- Existing data is assigned `ruleset_version = 0` during migration.
- Stored legacy sprint confidence may remain visible with an `Unversioned
  legacy result` label.
- Legacy release raw metrics may remain visible.
- Derived legacy release confidence is unavailable when it was not stored at
  original calculation time; it must not be reconstructed with version `1`
  rules.
- A current recomputation creates a new versioned snapshot without deleting the
  legacy record.

### Version change control

A behavioral ruleset change must update together:

1. This catalog and its version history.
2. The centralized runtime ruleset version.
3. The implementing services.
4. Boundary, empty-data, partial-data, and historical-version tests.
5. API contracts and user-facing documentation.

Continuous integration must reject a behavioral ruleset change when the
ruleset version has not been incremented.

### Schema migration safety

Application startup must bring the configured database to the current Alembic
revision before accepting API requests or starting scheduled work.

For an existing SQLite database created before Alembic version tracking:

1. The existing schema must match a known historical revision exactly enough
   to identify the latest completed revision.
2. A consistent database backup must be created before the first migration to
   the current revision.
3. The identified revision must be stamped without recreating tables or
   deleting application data, and all later migrations must then run in order.
4. An unknown or inconsistent schema must stop startup with an explicit error;
   the application must not guess a revision or continue with a partial schema.
5. Repeated startup at the current revision must be idempotent and must not
   create another backup.

Fresh databases must be created through the same Alembic migration chain. A
successful startup must leave the database stamped at the single current head.

## Change Control

Any change to a metric, signal, threshold, availability rule, or classification
must update, in the same change:

1. This catalog.
2. The implementing service.
3. Boundary, empty-data, and partial-data tests.
4. API schemas/examples when the contract changes.
5. User-facing product documentation.
6. The ruleset version when behavior or output meaning changes.

Business rules must not be introduced only in API routes, React components, or
PDF templates.

## Phase 0 Decision Register

| Point | Decision | Status |
|---|---|---|
| 0.1 | Use `PRODUCT_RULES.md` as the canonical product-rule catalog | Approved |
| 0.2 | Use the worse of hard-rule severity and weighted confidence-band severity | Approved |
| 0.3 | Return a partial score from 50% coverage; below 50% is inconclusive | Approved |
| 0.4 | Use Jira issue age and current uninterrupted risk age as separate facts | Approved |
| 0.5 | Replace prediction claims with a deterministic current Release Outlook | Approved |
| 0.6 | Use immutable snapshots and a monotonically increasing integer ruleset version | Approved |
