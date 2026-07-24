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
  inconsistent with another documented rule. The related product decision
  must be completed before behavioral changes are implemented.

## Documentation Ownership

Status: **Approved — Phase 1.1**

Each repository document has one explicit responsibility:

| Document | Responsibility |
|---|---|
| `AGENTS.md` | Engineering constraints and working rules for AI agents contributing to the repository |
| `PRODUCT_RULES.md` | Normative product behavior: metrics, signals, thresholds, availability, evidence, and versioning |
| `README.md` | Technical overview, architecture, API contract, development workflow, and concise product-rule summaries |
| `ABOUT.md` | User-facing product guidance and explanations of what each screen, metric, and decision aid means |
| `desktop/README.md` | Desktop build, packaging, migration, installation, recovery, and acceptance procedures |

The following precedence and maintenance rules apply:

1. `PRODUCT_RULES.md` is the source of truth for product behavior. Other
   documents may summarize its rules but must not redefine them.
2. `AGENTS.md` governs how repository work is performed. It does not override
   an approved product rule; a conflict must be reported and resolved
   explicitly.
3. API fields and examples in `README.md` must match the implemented schemas
   and the applicable ruleset version.
4. User language in `ABOUT.md` must describe only evidence the product can
   actually compute and display. It must not introduce stronger claims than
   the product rules allow.
5. Desktop operational behavior belongs in `desktop/README.md`; technical or
   product summaries should link to it instead of duplicating procedures.
6. When behavior changes, every affected owner document must be updated in the
   same change. A documentation conflict must never be resolved silently.

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

Status: **Approved — Phase 2.1**

Classifications are explicit Jira-instance configuration inputs. The approved
settings and compatibility defaults are:

| Setting | Default |
|---|---|
| `JIRA_DONE_STATUSES` | `done,closed,resolved` |
| `JIRA_IN_PROGRESS_STATUSES` | `in progress,in development,in review,in testing` |
| `JIRA_HIGH_SEVERITY_VALUES` | `high,highest,critical` |
| `JIRA_BUG_ISSUE_TYPES` | `bug` |
| `JIRA_BLOCKER_ISSUE_TYPES` | `blocker,incident` |
| `JIRA_BLOCKER_SEVERITY_VALUES` | `blocker,highest,critical` |
| `JIRA_BLOCKED_STATUSES` | `blocked` |

The following rules apply to every configured classification set:

1. Values are comma-separated, trimmed, compared case-insensitively, and
   deduplicated after case folding.
2. Done, in-progress, high-severity, and Bug sets must not be empty.
3. Done and in-progress status sets must not overlap after normalization.
4. Each blocker fallback set may be empty. This allows a Jira instance to
   disable a fallback category deliberately.
5. Invalid values supplied through the configuration API return `400` with an
   explicit reason. Invalid effective startup configuration stops startup
   rather than silently restoring defaults.

Blocker classification has explicit precedence:

1. When `JIRA_FIELD_BLOCKER` is configured and the issue supplies a value, its
   match against `JIRA_BLOCKER_TRUE_VALUES` decides the blocker flag.
2. When that explicit Jira value is absent, an issue is a blocker when its
   issue type, severity, or status matches the applicable configured blocker
   fallback set.
3. A done issue is not an open blocker even when its blocker flag or fallback
   classification is true.

Metrics must classify stored raw Jira status, issue-type, severity, and blocker
values using the effective configuration at recomputation time. They must not
rely only on a previously derived `issues.is_blocker` value, because that value
may have been produced under an older configuration.

Every release and sprint snapshot must store the complete normalized
classification sets and blocker precedence inputs in `calculation_provenance`.
Changing configuration affects only new immutable snapshots; historical
snapshots are never rewritten. A comparison between snapshots with different
effective classification sets is unavailable with an explicit reason rather
than presenting configuration changes as Jira delivery changes.

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

Status: **Approved — Phase 2.2**

- Scope: issues currently associated with the release.
- Formula: count issues whose explicit or fallback blocker classification is
  true and whose status is not done.
- Unit: tickets.
- Evidence: sorted matching Jira issue keys are stored on the metric snapshot.
- Required inputs: non-empty status and enough explicit-field or configured
  fallback data to determine blocker classification.
- Partial input: return the confirmed minimum count, mark the metric `PARTIAL`,
  and explain that additional blockers may exist.
- Empty scope: the API value is `null` and the metric is `NOT_COMPUTED`; an
  empty release must not present zero blockers as healthy evidence.

### Open high-severity bugs (`open_high_severity_bugs`)

Status: **Approved — Phase 2.2**

- Scope: issues currently associated with the release.
- Formula: count issues whose type matches a configured Bug issue type,
  severity matches a configured high-severity value, and status is not done.
- Unit: tickets.
- Evidence: sorted matching Jira issue keys are stored on the metric snapshot.
- Required inputs: non-empty issue type; severity for a ticket classified as a
  Bug; and status for a Bug with high severity.
- Partial input: return the confirmed minimum count, mark the metric `PARTIAL`,
  and explain that additional high-severity bugs may exist.
- Empty scope: the API value is `null` and the metric is `NOT_COMPUTED`.

### Scope completed (`scope_completed_pct`)

Status: **Approved — Phase 2.2**

- Formula: `100 * current done release tickets / current release tickets`.
- Unit: percent from `0` to `100`.
- Rounding: two decimal places.
- Every scoped ticket requires a non-empty status. If any status is missing,
  the value is `null` and the metric is `PARTIAL`; missing status is not
  silently treated as incomplete work.
- Empty scope: the API value is `null` and the metric is `NOT_COMPUTED`.
- Story points are not used.

### Completed tickets (`completed_tickets`)

Status: **Approved — Phase 2.2**

- Formula: count current release tickets whose status is done.
- Unit: tickets.
- Partial input: return the confirmed minimum count when any scoped ticket has
  no status, mark the metric `PARTIAL`, and explain that additional completed
  tickets may exist.
- Evidence: sorted confirmed completed-ticket keys are stored and exposed.
- Empty scope: the API value is `null` and the metric is `NOT_COMPUTED`.

### Release scope and risk evidence

Status: **Approved — Phase 2.2**

For the four metrics above, `calculation_provenance` stores sorted issue-key
lists for:

- evaluated tickets;
- matching tickets;
- missing status;
- missing issue type;
- missing severity; and
- indeterminate blocker classification.

Only lists applicable to a metric need to be populated, but every applicable
list must be present even when empty. A zero blocker, high-severity-bug, or
completed-ticket count is exact only when that metric is `COMPUTED`. A
`PARTIAL` count is explicitly a confirmed minimum, never an inferred complete
result.

### Scope churn, added scope, and removed scope

Fields: `scope_churn_7d_pct`, `scope_added_7d_count`,
`scope_removed_7d_count`

Status: **Approved — Phase 2.3**

The metric uses the stored snapshot time as its single calculation boundary:

- `window_end = snapshot_at`;
- `window_start = snapshot_at - 7 days`; and
- both UTC boundaries are inclusive.

No independent current-time call may be made inside the churn calculation.

The source is fix-version changelog records from synchronized issues in the
configured Jira project. A record qualifies only when its normalized field
name matches a configured fix-version changelog alias and its old and new
values prove a membership change for the exact release name,
case-insensitively:

- Added: the old value does not reference the release and the new value does.
- Removed: the old value references the release and the new value does not.
- A record that does not change release membership is ignored.

An issue can appear in both the added and removed evidence lists when it moves
more than once. It appears only once in the distinct churn numerator.

Definitions:

- `churned issue keys = distinct union of added and removed issue keys`;
- `observed scope issue keys = current release issue keys union churned issue
  keys`; and
- `scope_churn_7d_pct = 100 * churned issue count / observed scope issue
  count`.

The percentage is rounded to two decimal places and is naturally bounded from
`0` to `100`; it is not capped after calculation. Added and removed counts are
the lengths of their distinct evidence lists and can overlap.

Availability rules:

- Relevant changelog completeness covers every synchronized issue in the
  release's configured Jira project. Any project issue could contain a removal
  from the release, so checking only current or already-observed issue keys is
  insufficient.
- `COMPUTED`: observed scope exists and every synchronized project issue has
  complete Jira changelog ingestion.
- `PARTIAL`: any synchronized project issue has incomplete Jira changelog
  ingestion. Added and removed counts remain confirmed minimum counts, while
  `scope_churn_7d_pct` is `null`. This status also applies when no observed
  scope is currently known, because missing history may contain a qualifying
  membership change.
- `NOT_COMPUTED`: neither current scope nor qualifying changed scope exists and
  all synchronized project issue histories are complete.

Complete changelog ingestion with current scope but no qualifying changes
returns a meaningful `0%`. No current tickets with confirmed removals can still
produce a computed result. A partial or unavailable percentage must not be
replaced by zero in confidence, signal, readiness, or reporting calculations.

`calculation_provenance` stores the window boundaries, synchronized project
issue keys, current-scope keys, observed-scope keys and denominator, churned
keys, added keys, removed keys, incomplete-project-changelog keys, configured
changelog aliases, and normalized release value used by the calculation. Every
issue-key list is sorted.

### Median cycle time (`median_cycle_time_days`)

Status: **Approved — Phase 2.4**

Scope is current release membership whose current status is done. For each
eligible ticket:

1. Start is the earliest transition into a configured in-progress status.
2. End is the earliest transition into a configured done status strictly after
   that start.
3. This first valid pair is used even when an earlier done transition exists.
4. Duration is `(end - start) total seconds / 86,400` days.

The metric is the statistical median of valid ticket durations, rounded to
four decimal places.

Availability rules:

- `COMPUTED`: at least one valid pair exists and all potentially eligible
  ticket histories are complete.
- `PARTIAL`: a missing current status or incomplete Jira history could change
  the included tickets or median. The value is `null`.
- `NOT_COMPUTED`: evidence is complete but no valid transition pair exists.

`calculation_provenance` stores every included issue key, start, end, and
duration. Excluded issue keys are sorted and grouped by missing status,
incomplete history, no in-progress transition, no later done transition, or
invalid timestamps.

### Reopen event rate (`reopen_rate_pct`)

Status: **Approved — Phase 2.4**

The API field remains `reopen_rate_pct` for compatibility. Its approved
user-facing meaning is **reopen events per 100 eligible tickets**.

Eligible denominator:

`current scoped tickets that are currently done or have a recorded transition
into a configured done status`

Numerator:

`total distinct done-to-non-done transition events for eligible tickets`

Formula:

`100 * reopen event count / eligible ticket count`

A reopen event is a stored status transition whose normalized old status is
done and normalized new status is not done. Event identity is the unique
combination of issue key, transition timestamp, normalized old status, and
normalized new status. Duplicate copies of that identity count once.

Every distinct reopen event is counted. Multiple events for one ticket
therefore increase the numerator multiple times, and the result can exceed
`100%`; it is never capped. The value is rounded to two decimal places.

Availability rules:

- `COMPUTED`: at least one eligible ticket exists and all relevant current
  statuses and histories are complete.
- `PARTIAL`: missing status or incomplete Jira history could change the
  denominator or event count. Confirmed eligible and event counts remain
  available, but `reopen_rate_pct` is `null`.
- `NOT_COMPUTED`: evidence is complete but no scoped ticket has reached done.
- A complete result with eligible tickets and no reopen events is `0%`.

`calculation_provenance` stores sorted scoped and eligible issue keys, the
eligible denominator, every distinct reopen event, event count by issue key,
issue keys reopened multiple times, missing-status keys, and
incomplete-history keys. Events are ordered by issue key and transition time.

When any ticket has multiple reopen events, the API, UI, and reports state:
`Ticket {key} was counted {count} times because it was reopened {count} times.`

The same cycle-time and reopen-event-rate contracts apply to sprint metrics,
using current issue-to-sprint membership. Partial or unavailable values must
not be replaced by zero in confidence, signals, recommendations, or reports.

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
| Reopen event rate greater than `15%` | 6 |
| Reopen event rate greater than `10%`, otherwise | 3 |
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
- Reopen event rate greater than `15%`.

Hard YELLOW conditions, when no hard RED condition is active:

- Open high-severity bugs greater than `0`.
- Scope churn greater than `10%`.
- Reopen event rate greater than `10%`.
- Median cycle time greater than `7` days.

Hard-rule severity is GREEN when none of these conditions is active. All
comparisons are strict `>` comparisons, so a value exactly equal to a threshold
does not breach that threshold.

### Incomplete classification inputs

Status: **Approved — Phase 2.2**

When any classification-dependent release-confidence input is `PARTIAL`:

- `confidence_score` is `null` rather than being calculated from confirmed
  minimum risk counts;
- the release metrics response is `PARTIAL` and identifies every affected
  metric and missing Jira issue key;
- a confirmed hard RED condition still produces a final RED signal because
  missing information cannot reduce its severity; and
- without a confirmed hard RED condition, the final signal and Release Outlook
  are `INCONCLUSIVE` rather than GREEN, YELLOW, or an apparently healthy
  outlook.

`INCONCLUSIVE` is an availability state, not a fourth severity level. Reasons
must identify the incomplete inputs and retain any confirmed active risk
evidence.

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
4. Reopen event rate `<= 15%`.
5. Median cycle time is unavailable or `<= 7` days.

`readiness_pct = 100 * passed gates / total gates`.

## Sprint Metrics

### Current sprint scope (`committed_scope`)

Status: **Approved — Phase 2.5**

- The API field remains `committed_scope` for compatibility. Its approved
  user-facing label is **Current sprint scope**.
- Formula: count distinct current issue-to-sprint membership keys.
- Unit: tickets.
- This value is current membership at snapshot time and must not be described
  as sprint-start commitment.
- Evidence: sorted current membership keys are stored in provenance.
- Empty membership: the API value is `null` and status is `NOT_COMPUTED`.

### Completed scope (`completed_scope_pct`)

Status: **Approved — Phase 2.5**

- Formula: `100 * current done sprint tickets / current sprint tickets`.
- Unit: percent from `0` to `100`.
- Rounding: two decimal places.
- Every scoped ticket requires a non-empty status. If any status is missing,
  the value is `null` and the metric is `PARTIAL`.
- Empty scope: the API value is `null` and status is `NOT_COMPUTED`.
- Story points are not used.

### Sprint blockers and high-severity bugs

Fields: `open_blockers`, `open_high_severity_bugs`

Status: **Approved — Phases 2.2 and 2.5**

- These use the same classification, confirmed-minimum, partial-input, and
  empty-scope rules as their release equivalents.
- Scope is current issue-to-sprint membership.
- Sorted matching issue keys are stored on the sprint metric snapshot.

### Bugs created during sprint (`bugs_created_during_sprint`)

Status: **Approved — Phases 0.4 and 2.1**

- Count tickets with an issue type in the configured Bug issue-type set whose
  `jira_created_at` is between the sprint start and effective sprint end,
  inclusively.
- For a closed sprint, effective end is completion time when present, otherwise
  configured end time, otherwise snapshot time.
- For an active or other non-closed sprint, effective end is the earlier of
  configured end time and snapshot time, or snapshot time when no end exists.
- If sprint start is missing, the metric is unavailable.
- Tickets missing `jira_created_at` are not silently counted or discarded: the
  metric is marked partial and exposes their sorted Jira keys.
- Local database insertion time is never used by this metric.

### Work-state counts

Fields: `in_progress_count`, `not_started_count`

Status: **Approved — Phase 2.5**

- In progress: current sprint tickets in a configured in-progress status.
- Not started: current sprint tickets with a non-empty status in neither the
  configured done nor in-progress sets.
- Missing status produces confirmed-minimum counts marked `PARTIAL`; it is not
  classified as not started.
- Evidence stores sorted matching and missing-status issue keys.

### Unfinished closed-sprint scope (`rollover_count`)

Status: **Approved — Phase 2.5**

The API field remains `rollover_count` for compatibility. Its approved
user-facing label is **Unfinished closed-sprint scope**.

- The metric applies only when sprint state is `closed`.
- Formula: count current sprint-membership tickets whose current status is not
  done.
- The value does not prove that a ticket entered another sprint and must not be
  labelled rollover in the UI or reports.
- Active, future, or unknown-state sprints return `null` with metric status
  `NOT_APPLICABLE`.
- A closed sprint with no current scope returns `null` with `NOT_COMPUTED`.
- Missing status returns the confirmed minimum unfinished count with `PARTIAL`.
- A fully evidenced closed sprint with no unfinished tickets returns `0` with
  `COMPUTED`.
- Provenance stores sprint state, applicability, current membership keys,
  matching unfinished keys, and missing-status keys.

### Sprint median cycle time and reopen event rate

Fields: `median_cycle_time_days`, `reopen_rate_pct`

Status: **Approved — Phase 2.4**

- These use the same formulas, event identity, availability rules, and stored
  evidence as the release equivalents, scoped to current sprint membership.

## Sprint Delivery Confidence

Status: **Approved — Phases 0.3 and 2.5**

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

### Required non-point inputs

Status: **Approved — Phase 2.5**

Meeting the story-point coverage threshold is necessary but not sufficient to
calculate delivery confidence. The calculation also requires:

- non-empty status for every pointed current-sprint ticket used by progress
  alignment;
- complete blocker classification for the current sprint scope;
- a valid sprint duration with both start and end times and `end > start`; and
- complete sprint-membership changelog history for every synchronized issue in
  the sprint's Jira project, because a removed issue may no longer be in current
  membership.

If any required non-point input is missing, delivery-confidence status is
`INCONCLUSIVE`, `delivery_confidence_score` is `null`, and explanations list
the affected input and sorted Jira issue keys. This rule takes precedence over
the `PARTIAL` score allowed for story-point coverage from `50%` to below `100%`.
Partial story-point coverage still returns a score when all required non-point
inputs are complete.

Missing or invalid sprint duration makes both progress alignment and velocity
fit unavailable: elapsed percentage, remaining-time ratio, and remaining
capacity must not receive healthy fallback values. This duration requirement
does not change the independently approved windows for bugs created during the
sprint or scope stability.

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
- If duration is valid and elapsed time is exactly zero, component is `100`.
- If elapsed time is unavailable because duration is missing or invalid, the
  component is unavailable and delivery confidence is `INCONCLUSIVE`.

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

- Blocked ratio: `open blockers / current sprint-scope count`.
- Empty scope is `NOT_COMPUTED`; it is not assigned a zero blocked ratio for a
  delivery-confidence calculation.
- Component: `clamp(100 * (1 - blocked ratio), 0, 100)`.

#### Scope stability

- Post-start additions and removals are reconstructed from sprint changelog.
- Initial commitment count:
  `max(current ticket count - added count + removed count, 0)`.
- Stability index:
  `(added count + removed count) / initial commitment count`.
- Component: `clamp(100 * (1 - stability index), 0, 100)`.
- Missing sprint start or incomplete project sprint-membership history makes
  scope stability unavailable and delivery confidence `INCONCLUSIVE`; missing
  stability is never replaced by zero churn.

Delivery confidence formula:

`0.40 * progress alignment + 0.30 * velocity fit + 0.20 * blocker health + 0.10 * scope stability`.

### Ticket-based metrics during incomplete coverage

The following are evaluated independently because they are not calculated from
aggregated story points. Each can still be `PARTIAL`, `NOT_COMPUTED`, or
`NOT_APPLICABLE` under its own approved availability rules:

- current sprint-scope count and completed ticket percentage;
- open blockers and open high-severity bugs;
- bugs created during the sprint;
- in-progress, not-started, and unfinished closed-sprint counts when
  applicable;
- median cycle time and reopen event rate; and
- ticket-based scope movement and stability evidence.

### Workload distribution

Status: **Approved — Phase 2.5.4**

Workload distribution measures how concentrated active current-sprint work is
among assignees. Active tickets are current-sprint tickets whose non-empty
status is not in the configured done-status set. Every current-sprint ticket
requires a status; any missing status makes workload distribution
`INCONCLUSIVE` because the active scope is unknown.

Valid story points are finite, non-negative values. Null or blank assignees
belong to the explicit `Unassigned` bucket. Assigned users are grouped by their
stable Jira identifier when one is available. If Jira supplies no stable
identifier, the trimmed, case-insensitive display name is used as a fallback
and the result is marked `PARTIAL`. The displayed label for a fallback group is
the lexicographically first trimmed source value in that normalized group.

Availability rules:

- No current-sprint tickets: `NOT_COMPUTED` with a `null` value.
- Below `50%` current-sprint story-point coverage: `INCONCLUSIVE` with a `null`
  value.
- From `50%` up to but not including `100%`: use pointed active tickets,
  exclude unpointed active tickets, list the excluded keys, and mark the result
  `PARTIAL`.
- At `100%`: use the complete active sprint scope and mark the result
  `COMPUTED`, unless assignee-identity fallback makes it `PARTIAL`.
- No active tickets: `NOT_APPLICABLE` with a `null` value.
- Active tickets whose included story points sum to zero: `NOT_COMPUTED` with a
  `null` value; no concentration percentage is inferred.

For each assignee bucket, sum included active story points. Let
`total_active_points` be the sum across all buckets. Select the bucket with the
largest point total; ties are resolved by normalized assignee name in ascending
order. The metric is:

`workload_concentration_pct = 100 * top_assignee_points / total_active_points`.

The percentage is rounded to two decimal places. Risk bands are:

- below `35%`: healthy;
- from `35%` through `50%`: watch; and
- above `50%`: critical.

The `Reduce workload concentration` recommendation is generated when the
percentage is at least `35%`. It is not generated from an `INCONCLUSIVE`,
`NOT_COMPUTED`, or `NOT_APPLICABLE` result. A recommendation generated from a
`PARTIAL` result must carry the same partial-data explanation. Recommendation,
reporting, and frontend code consume the authoritative stored result and do
not independently recalculate it.

Stored evidence contains sorted current-scope, active, included-active,
excluded-active, missing-status, and assignee-identity-fallback issue keys;
story-point totals per assignee; total included active points; top assignee and
its points; the percentage; story-point coverage; and calculation status.

### Persistence and API evidence

Sprint snapshots must store:

- total, pointed, and unpointed current-sprint ticket counts;
- story-point coverage percentage and sorted unpointed ticket keys;
- delivery-confidence status: `NOT_COMPUTED`, `INCONCLUSIVE`, `PARTIAL`, or
  `COMPUTED`;
- the score when calculated;
- component values and calculation inputs; and
- historical baseline identifiers and coverage details;
- workload-concentration percentage, status, and explanations; and
- structured workload-distribution evidence.

This evidence must be returned by the API so every score and unavailable state
remains explainable and reproducible.

## Metric Availability

Status: **Approved — Phases 0.3 and 2.2–2.5**

- No scoped tickets: computation status is `NOT_COMPUTED`.
- Tickets exist but no snapshot exists: `NOT_COMPUTED`.
- Snapshot exists but one or more metric dependencies are missing: `PARTIAL`.
- All dependencies exist: `COMPUTED`.
- Classification-dependent release metrics follow the per-metric required-input
  and partial-value rules above.
- Scope churn follows its observed-scope and changelog-completeness rules; the
  absence of changelog rows is not itself evidence that the metric is
  unavailable.
- Other changelog-based metrics follow their metric-specific completeness
  rules.
- Sprint delivery-confidence availability and status follow the story-point
  coverage rules above. The delivery-confidence status does not suppress
  otherwise available ticket-based metrics.
- Median cycle time and reopen event rate follow their valid-pair,
  eligible-denominator, and history-completeness rules above.

APIs must expose unavailable values explicitly and must not replace unknown or
unavailable values with inferred healthy values.

Every metric-availability item exposes `status`, explicit explanations, and
sorted missing issue keys. The existing `available`, `reason`, and `depends_on`
fields remain for API compatibility. `status` is authoritative; `available` is
true when a computed or confirmed-partial value is returned and false when the
metric value is `null`.

`NOT_APPLICABLE` is a metric-level availability status for a metric that does
not apply to the entity's current state, such as unfinished closed-sprint scope
for an active sprint. It returns a `null` value and `available = false`, and it
does not make the overall response `PARTIAL`.

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
| Inconclusive | `INCONCLUSIVE` |
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
- Version `2` identifies the approved Phase 2 metric-contract hardening once
  that contract is implemented in runtime code.
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

## Schema Authority and Migration Entry Point

Status: **Approved — Phase 3.1**

Alembic is the only runtime mechanism allowed to create or modify LighthousePM
application tables, columns, constraints, and indexes. This rule applies to
both configured database dialects: PostgreSQL and SQLite.

- Application startup must always upgrade the configured database to the
  single current Alembic head before API readiness or scheduled work.
- `Base.metadata.create_all()` may be used only by isolated test fixtures. It
  must not be reachable through the application startup path.
- Runtime compatibility `ALTER TABLE`, `CREATE INDEX`, or other schema-repair
  statements outside ordered Alembic revisions are prohibited.
- Every schema change requires an ordered Alembic revision that handles both
  configured database dialects. Any intentional dialect-specific operation
  must remain explicit inside that revision.
- A fresh database is created by upgrading an empty database through the
  complete migration chain.
- A versioned database upgrades from its recorded revision.
- An unversioned database may be stamped only after deterministic schema
  identification proves a recognized historical revision.
- Unknown, partial, inconsistent, or multi-head states must stop startup with
  an explicit error. The application must not guess, repair, or continue with
  a partially migrated schema.
- Migration failure must prevent the scheduler, API readiness, and desktop
  workspace from starting.

Making the migration entry point authoritative does not change metric formulas,
thresholds, availability, or output meaning. The runtime `ruleset_version`
therefore remains `2`.

## Desktop Migration Readiness Gate

Status: **Approved — Phase 3.2**

For the managed desktop application, migration is a mandatory backend-readiness
gate. Electron may create the local backend operating-system process so that it
can run its startup lifecycle, but that backend must not report ready and the
desktop workspace must not open until migration reaches the single current
Alembic head successfully.

The startup order is deterministic:

1. Validate the effective backend startup configuration.
2. Upgrade the configured database to the single current Alembic head.
3. Start scheduled work.
4. Complete API startup and allow the health endpoint to report ready.
5. Load the desktop workspace after Electron observes successful health.

The same readiness gate applies to initial desktop startup and every
desktop-managed backend restart, including restarts after backup restore, local
data clearing, and factory reset.

If configuration validation or migration fails:

- scheduled work must not start;
- API health must not report ready;
- the desktop workspace must not open;
- Electron must show the backend-startup error state and direct the user to the
  backend log; and
- the desktop must not automatically clear, reset, restore, or otherwise guess
  how to repair the database.

A successful health response is the desktop's proof that the backend startup
lifecycle, including migration, has completed. The health endpoint is not a
second migration mechanism and must not contain schema-changing logic.

This readiness contract changes startup ordering and failure handling only. It
does not change metric formulas, thresholds, availability, or output meaning,
so the runtime `ruleset_version` remains `2`.

## Supported Schema Upgrade Matrix

Status: **Approved — Phase 3.3**

Every non-head revision retained in the single Alembic ancestor chain is a
supported versioned upgrade source. With current head `20260724_0019`, the
supported prior versioned revisions are `20260407_0001` through
`20260724_0018`. The current head is also a supported startup source and must
remain idempotent.

Supported unversioned legacy schemas are limited to the explicit deterministic
legacy-shape registry. The current registry recognizes schema milestones
`20260407_0001` through `20260716_0010`. An unversioned schema outside that
registry is not implicitly supported merely because it resembles a newer or
older database.

Unknown Alembic revisions and unknown, incomplete, or inconsistent unversioned
schemas must continue to fail closed. A supported source may be removed only by
an explicit compatibility decision that updates this catalog, the technical and
desktop documentation, and the upgrade-test matrix together.

Automated upgrade coverage must be derived from the Alembic graph and the
legacy-shape registry so a new revision or supported legacy shape cannot be
added without becoming a required test source. For every supported starting
state, the applicable matrix must verify that:

1. migration reaches the single current Alembic head;
2. representative data that existed at the source revision is preserved;
3. the resulting schema contains the expected current tables and columns;
4. an existing file-backed SQLite database produces its required
   pre-migration backup;
5. a second startup is idempotent; and
6. failure does not silently stamp, skip, or repair an unsupported state.

The complete versioned-revision matrix must run against both file-backed SQLite
and a real PostgreSQL instance. PostgreSQL behavior must not be inferred from
SQLite. The unversioned legacy-shape matrix is required for SQLite because that
is the supported pre-Alembic desktop adoption path.

Downgrades are not a supported desktop recovery mechanism and are not part of
the supported-source matrix. Migration-specific upgrade/downgrade round-trip
tests may remain as additional checks, but they do not replace full-chain
upgrade coverage from each supported source.

This matrix changes upgrade assurance only. It does not change product metrics,
signals, thresholds, or output meaning, so the runtime `ruleset_version`
remains `2`.

## Clean-Install and Existing-Database Startup Acceptance

Status: **Approved — Phase 3.4**

Schema correctness must also be verified through the real application startup
boundary. Direct calls to the migration orchestrator and per-revision tests do
not replace clean-install and existing-database startup acceptance.

An isolated clean startup must begin without an application database or data
directory and verify that:

1. the required parent directory and database are created;
2. the database reaches the single current Alembic head through the complete
   migration chain;
3. application health reports ready only after migration;
4. empty public API collections return their structured empty contracts;
5. no pre-migration backup is created for the new database; and
6. startup succeeds without Jira credentials when Jira sync is disabled.

An existing database already at the current head must start without a schema
rewrite or migration backup. Representative release, sprint, issue, metric, and
signal records must remain readable through the application APIs, and repeated
startup must remain idempotent.

An existing supported older database must verify that migration completes
before readiness, the required SQLite pre-migration backup is created, related
representative records survive, and the preserved records are readable through
the public APIs. A second startup must not recreate or overwrite the backup.

Application-level automated coverage must include:

- file-backed SQLite clean, current-head, and supported older versioned states;
- a recognized unversioned SQLite state;
- real PostgreSQL clean and supported older versioned states; and
- the actual desktop backend entry point with temporary SQLite storage,
  successful health polling, authenticated API access, and clean process
  termination.

The Phase 3.3 matrix remains responsible for exhaustive per-revision migration
coverage. Phase 3.4 uses representative older databases to prove the complete
startup and API boundary rather than duplicating that matrix.

Packaged Windows acceptance has two required paths:

1. A genuinely clean install with no existing LighthousePM user-data directory.
2. Installation over a previous LighthousePM version containing synchronized
   data and valid configuration.

The upgrade path must preserve the active database, `backend.env`, and encrypted
Jira token. Acceptance must confirm preserved data in the workspace; a running
process alone is not sufficient evidence. Automated tests and acceptance runs
must use isolated temporary storage or disposable PostgreSQL databases and must
never modify developer or production application data.

This startup-acceptance contract changes upgrade assurance only. It does not
change metrics, signals, thresholds, or output meaning, so the runtime
`ruleset_version` remains `2`.

## Atomic SQLite Migration Backups

Status: **Approved — Phase 3.5**

Before migrating an existing file-backed SQLite database, LighthousePM must
create and atomically publish a consistent pre-migration backup.

The backup must be created with SQLite's online backup operation and written
to a uniquely named temporary file in the same directory as the active
database. The temporary backup must be flushed and closed before it is
atomically published as `<database>.pre-<target-revision>.bak`. Alembic
stamping or migration must not begin until publication succeeds.

If copying, flushing, closing, or publishing the backup fails:

- startup must stop with an explicit error;
- Alembic stamping and migration must not begin;
- no new canonical `.pre-<revision>.bak` file may be exposed;
- the active database must remain at its original revision;
- the temporary file from that attempt must be removed when possible; and
- any remaining temporary file is non-authoritative, must never be treated as
  a valid migration backup, and must not prevent a later retry.

An existing canonical backup for the same target revision must never be
overwritten. Repeated startup reuses that canonical backup. Phase 3.5 does not
determine whether a pre-existing canonical backup is valid; integrity and
revision validation are defined separately by Phase 3.6. Migration startup is
a single-writer operation, and a concurrent attempt must not replace an
already published backup.

Automatic migration backups apply only to an existing application schema in a
file-backed SQLite database that requires migration. They are not created for
a fresh database, an in-memory or URI-managed SQLite database, PostgreSQL, or
a database already at the current Alembic head.

Automated coverage must verify successful atomic publication with no temporary
file left behind; copy and publication failures before migration; preservation
of the source revision and data after failure; rejection of stale temporary
files as backups; successful retry; preservation of an existing canonical
backup; inclusion of committed WAL-resident data; and unchanged fresh-database
and current-head behavior. Existing migration-matrix and application-startup
coverage must continue to pass.

This backup-publication contract changes operational safety only. It does not
change metrics, signals, thresholds, or API meaning, so the runtime
`ruleset_version` remains `2`.

## Backup Version and Integrity Validation

Status: **Approved — Phase 3.6**

Backup validation applies at three boundaries: before an automatic migration
backup is published or reused, before an automatic migration backup is copied
back manually, and before Electron restores a Settings backup.

### Automatic migration backups

A newly created temporary backup and an existing canonical backup must be
validated read-only before they can authorize migration. The backup must be a
regular readable SQLite file, and `PRAGMA integrity_check` must return exactly
`ok`. Its schema identity must be deterministically established as exactly one
known Alembic revision or a recognized unversioned legacy schema.

The backup's source revision must match the active database's pre-migration
revision and must be a supported ancestor of the target revision. The
canonical filename's target revision must match the current migration target.
A new temporary backup is validated before atomic publication; an existing
canonical backup is validated before reuse.

Validation failure must stop startup before Alembic stamping or migration. The
active database and backup remain unchanged, and the invalid backup must not be
deleted, replaced, or silently repaired. The error must identify the backup
path and the failed rule so the user can preserve or explicitly move the
invalid file before retrying.

Automatic `.pre-<revision>.bak` files remain outside Settings Restore. Before
manual replacement of the active database, a local validator must report the
SQLite integrity result, recorded or inferred source revision, revision
identity type (`alembic` or `recognized_legacy`), filename target revision,
compatibility with the installed migration chain, and a final `VALID` or
`INVALID` result. Corrupt, unknown, unsupported, mismatched, or future
revisions must produce an unsuccessful exit status. Recovery instructions must
not recommend copying an unvalidated backup.

### Settings backup format version 2

New Settings backups use manifest version `2`. The manifest must record
`app: "LighthousePM"`, `version: 2`, a creation timestamp, every included
relative file path, exact byte size and SHA-256 digest for every payload, and
the database revision plus revision-identity type when a database is included.

Allowed payload paths are limited to:

- `data/lighthouse.db`;
- `backend.env`; and
- `secrets/jira-token.bin`.

The database payload must be a consistent standalone SQLite backup. Version 2
does not include WAL or SHM files. The manifest must be written last and
atomically; a directory without its completed manifest is not selectable for
restore. SHA-256 detects accidental file changes but does not authenticate a
backup against deliberate coordinated modification.

Manifest version `1` lacks stored file hashes and does not satisfy this
integrity contract. Version-1 backups must be preserved but rejected by
automatic restore with an explicit legacy-format explanation. Unknown,
missing, malformed, zero, negative, and future versions also fail closed. The
application must not silently add hashes to a legacy manifest and thereby
bless its current contents without evidence of their original integrity.

### Settings restore preflight

Before stopping the backend or modifying any active file, Electron must
validate the selected backup completely:

1. The manifest is valid JSON with the expected application and supported
   version.
2. Every payload path belongs to the fixed allowlist and remains inside the
   backup directory.
3. Every declared payload is a regular file, and no declared file is missing.
4. Every byte size and SHA-256 digest matches the manifest.
5. The SQLite database passes `integrity_check`.
6. Its actual revision matches the manifest and is supported by the installed
   migration chain.
7. `backend.env`, when present, is readable UTF-8 and structurally valid.
8. The encrypted token, when present, is decryptable for the current operating
   system account.

Validation is all-or-nothing. On failure, the backend remains running; the
active database, WAL, SHM, configuration, and token remain unchanged; and the
UI identifies the selected path and failed validation rule.

After successful validation, the backend is stopped. A restored database
replaces the active database as a set, stale active WAL and SHM files are
removed, optional configuration and token files are replaced only when they
are included, and restart uses the established migration-readiness gate.
Transactional rollback for a failure after validated replacement begins is
defined separately by Phase 3.7.

Automated coverage must include valid new and reused migration backups;
corrupt, truncated, non-SQLite, unreadable, unknown, future, and mismatched
backups; recognized legacy schemas; validation before publication and before
migration; manual-validator output and exit status; valid version-2 creation
and restore; manifest-last publication; malformed manifests and versions;
missing, changed, escaping, or linked payloads; database, configuration, and
token validation; preflight before backend shutdown; stale WAL/SHM removal;
explicit user-facing errors; and existing migration, startup, desktop, and
backend regressions.

This validation contract changes operational backup safety only. It does not
change metrics, signals, thresholds, API meaning, or output meaning, so the
runtime `ruleset_version` remains `2`.

## Transactional Desktop Storage Operations and Recovery Tests

Status: **Approved — Phase 3.7**

Settings Restore, Clear Data, and Factory Reset must execute as transactional
desktop storage operations. Validation alone is not sufficient: a failure
after active-file mutation begins must restore the previous usable state.

### Operation lifecycle

Each operation must:

1. acquire the single desktop-storage operation lock;
2. validate every operation input;
3. stop the backend and confirm process exit within a bounded timeout;
4. create and validate a recovery snapshot before the first active-file
   mutation;
5. atomically publish an operation journal;
6. apply the requested changes;
7. start the backend through the established migration-readiness gate;
8. verify operation-specific postconditions; and
9. mark the operation committed and remove its recovery data.

A fixed delay is not proof that the backend released SQLite. If shutdown cannot
be confirmed, the operation must abort without modifying active files.
Concurrent desktop-storage operations must be rejected explicitly.

### Recovery journal and interrupted-operation recovery

Every destructive operation must use a unique directory under
`%APPDATA%\LighthousePM\recovery\<operation-id>\`. Its atomically published
manifest records the journal format version, operation type and identifier,
current state, original presence or absence of each affected path, recovery
payload sizes and SHA-256 digests, creation time, and last state transition.

Recovery journals are internal rollback artifacts, not Settings backups. They
must never be selectable by Settings Restore. At most one unfinished journal
may exist; multiple, malformed, incomplete, or checksum-invalid journals fail
closed.

Electron must inspect recovery state before starting the backend. When one
valid unfinished journal exists, Electron restores the previous active state,
removes files that were originally absent, verifies restored files, and starts
the backend only after rollback completes. The journal may be removed only
after readiness confirms that the previous state works.

If rollback fails, the backend and workspace remain closed, recovery files and
diagnostics are preserved, and the error identifies the journal path and failed
rule. This automatic recovery applies only to explicitly journaled desktop
operations. Schema migration failure must not trigger automatic restoration of
an automatic migration backup.

### Operation-specific outcomes

Settings Backup remains non-destructive and does not create a recovery journal.
A failed backup must leave no selectable manifest and must not alter the active
files or running backend.

After Settings Restore preflight succeeds, every active path that will be
replaced must be recoverable. Optional files absent from the selected backup
remain unchanged. A restored database removes stale active WAL and SHM files,
and success requires backend readiness plus restored data through the public
APIs. Replacement or restart failure must restore and restart the previous
state. The UI reports that restore failed and the previous state was restored;
it must not report restore success.

Clear Data succeeds only when the active database, WAL, and SHM have been
removed, a fresh empty database reaches the current head, and public APIs return
structured empty results. Configuration, encrypted token, logs, and automatic
migration backups remain. Deletion or restart failure restores and verifies the
original database set.

Factory Reset succeeds only when the active database set, configuration,
encrypted token, and previous logs are removed; automatic migration backups
remain; a fresh current-head database is created; and the application returns
to first-run configuration. New startup logging may begin after the previous
logs are removed. Reset or restart failure restores the original database,
configuration, token, and prior logs, preserves failure diagnostics separately,
and verifies the previous backend state.

When operation rollback succeeds, the requested operation still reports
failure with an explicit `previous state restored` explanation. When rollback
or rollback restart fails, recovery artifacts remain and the workspace stays
closed.

### Automated and packaged acceptance coverage

Automated tests must cover representative older-version startup; valid backup
and restore round trips; database-only and optional-file combinations; backup
failure before manifest publication; preflight failure while the backend stays
running; failure at every replacement boundary; restart failure; successful
rollback and previous-state readiness; rollback-copy and rollback-restart
failure; interruption at every journal state and next-start recovery; invalid,
missing, duplicate, and corrupt journals; Clear Data and Factory Reset success
and rollback; automatic-backup retention; stale WAL/SHM removal; concurrent
operation rejection; exact user messages; and isolation from real application
data.

The exhaustive Alembic source matrix remains Phase 3.3's responsibility.
Phase 3.7 uses representative source revisions and verifies complete lifecycle
outcomes instead of duplicating the matrix.

Both clean-install and upgrade packaged-Windows reports must additionally
verify Settings backup creation after synchronized data is visible, local-data
change or clearing, restore with visible data and usable configuration/token,
Clear Data with empty APIs and retained settings, Factory Reset with first-run
state, and retention of automatic migration backups after both reset actions.

This contract changes desktop operational safety only. It does not change
metrics, signals, thresholds, API meaning, or output meaning, so the runtime
`ruleset_version` remains `2`.

## Supported Deployment-Mode Security Contract

Status: **Approved — Phase 4.1**

LighthousePM supports exactly three deployment modes. Each mode has an
explicit security boundary; security behavior must not be inferred only from
`APP_ENV`.

### Desktop-only mode

The packaged Electron application owns the complete local runtime:

- Electron starts and stops the FastAPI backend.
- The backend uses managed SQLite storage.
- The backend listens only on a loopback address and an Electron-selected
  port.
- Electron generates a new high-entropy API token for every backend process.
- All non-exempt API requests require that token.
- The token is passed directly to the backend process and is never persisted.
- Jira credentials are encrypted using operating-system-backed Electron
  storage.
- The renderer receives neither the local API token nor the decrypted Jira
  token.
- CORS is disabled because Electron proxies authenticated requests.
- The backend and workspace fail closed when authentication or security
  configuration is invalid.

The desktop backend is not a general network server and must never bind to a
LAN or public interface.

### Local-browser mode

The backend and browser frontend are started directly by a developer or local
operator:

- Backend and frontend bind to loopback by default.
- PostgreSQL or SQLite may be used.
- Anonymous API access is permitted only when `APP_ENV` is `dev` or `test`,
  the backend is bound exclusively to loopback, and the deployment is not
  treated as production.
- Production mode always requires an API token, including on loopback.
- Any non-loopback binding requires an API token regardless of `APP_ENV`.
- CORS contains only explicitly configured origins; wildcard origins are
  unsupported.
- This mode is not intended for direct public-internet exposure.
- Jira and API credentials must not be embedded in the frontend build.

Secure non-Electron credential persistence is defined separately by a later
Phase 4 point.

### Docker mode

The repository Compose deployment is a local Docker deployment by default:

- The backend may listen on the container interface, but its host port is
  published to `127.0.0.1` by default.
- PostgreSQL is private to the Compose network by default. If a host port is
  needed for administration, it is published to `127.0.0.1`, never all
  interfaces.
- Database credentials, Jira credentials, and API tokens are supplied at
  runtime and are not built into images.
- The browser frontend must not contain a reusable API secret.
- Production or externally reachable Docker deployments require API
  authentication.
- CORS must list the exact browser origins.
- Direct public-internet exposure without an authenticated TLS reverse proxy
  is unsupported.
- PostgreSQL must never be exposed to a public or untrusted network by the
  default project configuration.

### Shared expectations

Across all three modes:

- `/health` may remain unauthenticated only as a minimal liveness/readiness
  response containing no sensitive configuration.
- CORS is not authentication.
- API tokens are sent through the `Authorization: Bearer` header, never query
  parameters.
- Invalid production or network-exposure security configuration prevents
  startup.
- Mutating, configuration, synchronization, recomputation, and administrative
  operations receive explicit protection in later Phase 4 points.
- Secrets must not appear in logs, persisted error details, API responses,
  reports, URLs, or frontend bundles.
- Direct public deployment of FastAPI or PostgreSQL without an explicitly
  documented protective boundary is unsupported.

This contract defines supported security boundaries only. It does not change
metrics, signals, thresholds, availability, or output meaning, so the runtime
`ruleset_version` remains `2`.

## API-Token Requirements by Deployment Mode

Status: **Approved — Phase 4.2**

LighthousePM determines its authentication requirement explicitly from the
deployment mode, application environment, and effective backend bind address.
Supported backend launch paths provide the deployment mode (`desktop`,
`local-browser`, or `docker`), effective bind host, `APP_ENV`, and the local API
token when required. Security behavior must not depend on guessing how the
process was launched.

### Token-required rule

A non-empty API token is mandatory when any of these conditions is true:

- `APP_ENV=prod`;
- the effective bind host is not loopback;
- deployment mode is `desktop`; or
- deployment mode is `docker`, because the backend listens on the container
  network interface.

The resulting mode contract is:

| Mode | Environment and binding | Token requirement |
|---|---|---|
| Desktop | Production, loopback only | Required |
| Local browser | `dev` or `test`, loopback only | Optional |
| Local browser | Production or non-loopback | Required |
| Docker | Every supported configuration | Required |

Only `127.0.0.1`, `::1`, and `localhost` count as loopback bind values.
Values including `0.0.0.0`, `::`, LAN addresses, other hostnames, empty
values, and unknown values are non-loopback or invalid and cannot weaken the
authentication requirement.

### Startup enforcement

When a token is required but missing, configuration validation fails before
migration, scheduled work does not start, API readiness is not reached, and
the desktop workspace does not open. The error identifies the missing security
setting without printing secret values. A production or non-loopback server
must never start temporarily without authentication.

### Request enforcement

When authentication is required:

- every API endpoint except the minimal `/health` endpoint requires
  `Authorization: Bearer <token>`;
- comparison is constant-time;
- missing, malformed, or incorrect credentials return `401`;
- authentication failures return a generic structured error with
  `Cache-Control: no-store`;
- query parameters, cookies, and request bodies do not authenticate a
  request; and
- CORS does not bypass authentication.

In loopback-only `dev` or `test` local-browser mode, authentication may be
omitted. If a token is configured in that optional case, all protected
endpoints still require it.

Tokens are trimmed only for presence validation and are otherwise opaque.
Operational documentation recommends at least 32 cryptographically random
bytes rather than a human-readable password. Tokens must not be logged,
returned through APIs, persisted in application data, or embedded in frontend
bundles. Desktop tokens remain per-process and memory-only. Browser handling
and non-Electron persistence are defined by a later Phase 4 point.

This authentication contract does not change metrics, signals, thresholds,
availability, or output meaning, so the runtime `ruleset_version` remains `2`.

## Secure Docker Network Defaults

Status: **Approved — Phase 4.3**

The repository's base Compose configuration represents a local Docker
deployment and must not expose services to the LAN automatically.

### Backend exposure

The backend container listens on `0.0.0.0:8000` inside its private container
network so Docker can forward traffic to it. The default host mapping is
loopback-only:

```yaml
ports:
  - "127.0.0.1:${LIGHTHOUSE_BACKEND_PORT:-8000}:8000"
```

This default permits browser access from the same host but not from other LAN
devices. Binding the host side to `0.0.0.0`, `::`, a LAN address, or another
non-loopback interface is an explicit operator action and remains subject to
the Phase 4.2 authentication requirements. Docker mode always requires an API
token because the backend process binds to the container network interface.

### PostgreSQL exposure

The base Compose configuration does not publish PostgreSQL to the host.
PostgreSQL is accessible only to the backend through the private Compose
network and through explicit administration commands such as
`docker compose exec postgres psql`.

When a host PostgreSQL connection is genuinely required, a separate opt-in
local override may publish:

```yaml
ports:
  - "127.0.0.1:${LIGHTHOUSE_POSTGRES_PORT:-5432}:5432"
```

The project must not provide a default `5432:5432` mapping.

### Docker security identity and network scope

The backend container receives explicit settings identifying deployment mode
as `docker`, the effective container bind host as `0.0.0.0`, its application
environment, and its required API token. Compose interpolation or backend
startup fails when the required token is absent; Docker must not silently start
an anonymous API.

Compose uses a project-private network. PostgreSQL is not attached to an
external network by default, and neither service is published on an IPv6
wildcard address. CORS contains only exact local frontend origins. The base
configuration is not suitable for direct public-internet deployment. External
deployment requires an explicit override, API authentication, restrictive
CORS, and an authenticated TLS reverse proxy.

Operational documentation explains how to generate and supply the API token,
the loopback-only default API URL, PostgreSQL administration without a host
port, the optional loopback-only PostgreSQL override, and the security-boundary
change caused by non-loopback publishing. Database and API secrets must not be
committed.

Automated checks verify the explicit backend loopback host mapping, absence of
a PostgreSQL host port in the base file, loopback-only binding in the optional
PostgreSQL override, declared Docker mode and bind host, required Docker API
token, successful `docker compose config` with isolated test credentials, and
documentation that does not describe the defaults as LAN- or publicly
accessible.

This infrastructure contract does not change metrics, signals, thresholds,
availability, or output meaning, so the runtime `ruleset_version` remains `2`.

## Mutating and Administrative Endpoint Protection

Status: **Approved — Phase 4.4**

Every application route belongs to one explicit security class. A route must
not acquire security behavior implicitly from its HTTP method or module
location.

### Route classes

`GET /health` is the only public-health route. It remains unauthenticated and
returns no configuration, credentials, database details, internal paths, or
operational history.

Protected-read routes comprise ordinary dashboard and reporting reads,
including releases, sprints, issues, metrics, signals, charts, comparisons,
history, generated reports, and documentation. When Phase 4.2 requires
authentication, these routes require the API token.

Privileged-operation routes include:

- `GET /config/jira`;
- `PUT /config/jira`;
- `POST /config/jira/test`;
- `GET /admin/status`;
- `POST /sync/jira`;
- release recomputation endpoints;
- sprint recomputation endpoints; and
- any future route that writes configuration, starts external work, changes
  stored state, exposes operational details, or performs administrative work.

Privileged routes require authentication whenever the deployment requires
authentication or a token has been configured.

Loopback-only `dev` or `test` local-browser mode may remain fully anonymous
when no token is configured, as approved in Phase 4.2. This mode trusts the
local operating-system user and is not a read-only security boundary.
Configuring a token immediately protects both read and privileged routes.

### Centralized enforcement and privileged safeguards

Route classification and authentication are enforced centrally; business
logic does not move into API routes. A new route declares or inherits exactly
one class. Tests compare the complete FastAPI route inventory with the security
classification inventory, and an unclassified route fails instead of silently
becoming public. Authentication occurs before bodies containing credentials
are processed.

Configuration writes accept only the documented structured JSON contract.
Configuration and connection-test responses never return the Jira API token.
Authentication values in bodies or query parameters do not authenticate a
request. Configuration, administrative, and mutating responses use
`Cache-Control: no-store`. Valid protected reads do not change stored state.
Unsupported methods continue to return `405`, and privileged-operation errors
are sanitized without credentials or authorization values.

### Authorization scope

LighthousePM does not introduce accounts, roles, or a second administrator
token in this phase. The configured bearer token represents one trusted
LighthousePM operator and authorizes protected reads and privileged operations.
Deployments requiring separate users, read-only users, or role-based
administration must use an external authentication and authorization proxy;
native multi-user authorization is not supported.

Automated tests verify the single public route, complete and exclusive route
classification, token rejection and acceptance across both protected classes,
no authentication through bodies or query strings, `Cache-Control: no-store`
on sensitive responses, absence of token values from configuration responses,
read-only behavior for protected GET operations, and failure when a new route
is not deliberately classified.

This API-security contract does not change metrics, signals, thresholds,
availability, or output meaning, so the runtime `ruleset_version` remains `2`.

## Secure Non-Electron Credential Persistence

Status: **Approved — Phase 4.5**

Non-Electron deployments must not imitate Electron `safeStorage` without an
equivalent secure key store. Encrypting a secret while storing its encryption
key beside it is not secure persistence. This contract covers the LighthousePM
API bearer token, Jira API token, and Docker/PostgreSQL credentials. Non-secret
Jira settings may continue using the configured environment file.

### Server-side secret sources

Local-browser and Docker deployments obtain secrets, in order of supported
source type, from an explicitly configured mounted secret file, a process
environment variable, or a development-only `.env` file in loopback-only
`dev` or `test`. File-backed settings use explicit names such as:

```text
LIGHTHOUSE_API_TOKEN_FILE=/run/secrets/lighthouse_api_token
JIRA_API_TOKEN_FILE=/run/secrets/jira_api_token
POSTGRES_PASSWORD_FILE=/run/secrets/postgres_password
```

A direct value and its corresponding `*_FILE` setting must not both be
configured. Ambiguous sources fail startup.

A configured secret file resolves to an existing readable regular file, has a
bounded size, and contains a non-empty value after removal of one trailing line
ending. Invalid files fail startup with the setting name but not the secret.
The effective value is retained only in process memory and is not copied into
`.env`, SQLite, reports, or logs.

### Local-browser and Docker persistence

Production local-browser deployments provision API and Jira tokens through
the process environment or protected secret files. The Settings API persists
only non-secret configuration. `PUT /config/jira` rejects attempts to persist
a Jira token and directs the operator to the deployment secret provider.
`POST /config/jira/test` may accept a candidate Jira token for that request
only and does not persist it. A durable token change requires updating the
external source and restarting the backend.

Loopback-only `dev` or `test` may use a gitignored `.env` file as a documented
development convenience, not as production secret storage. Responses never
return secret values in any environment.

Docker uses mounted Compose secrets or equivalent read-only files for the
LighthousePM API token, Jira API token when Jira sync is enabled, and
PostgreSQL password. Secrets are not written into Compose configuration,
committed environment files, image layers, frontend build variables, or
container health checks. Operational documentation provides commands for
creating local secret files outside version control.

### Browser bearer-token handling

The browser receives the LighthousePM API token from the operator, never from
the frontend bundle or a public backend endpoint. The frontend retains it only
for the active browser session: in memory by default, optionally in
`sessionStorage` for same-tab reloads, and never in `localStorage`, IndexedDB,
service-worker caches, URLs, analytics, or logs. Closing the tab or browser
session removes the client-side token. Long-lived browser-token persistence is
delegated to an external authenticated reverse proxy or credential manager.

### Desktop and configuration-write behavior

Desktop behavior remains Electron-managed: Electron generates the local API
token per backend process, persists the Jira token through `safeStorage`, and
does not expose either decrypted secret to the renderer. The backend does not
persist desktop secrets itself.

The backend knows its deployment mode before processing configuration writes.
Desktop mode permits the Electron-managed Jira-token flow. Non-Electron modes
reject durable Jira-token writes but may use a transient candidate for a
connection test. Non-secret updates remain deterministic and atomic, and
responses expose only configured/not-configured booleans.

Automated tests cover direct environment values; valid, missing, empty,
oversized, unreadable, and conflicting secret files; absence of secret values
from errors, responses, logs, and configuration; rejected non-Electron token
persistence; transient connection testing; unchanged Electron `safeStorage`
behavior; Docker secret declarations without committed values; and frontend
bearer-token storage restrictions.

This credential contract does not change metrics, signals, thresholds,
availability, or output meaning, so the runtime `ruleset_version` remains `2`.

## Deployment-Mode Authentication and Configuration-Write Tests

Status: **Approved — Phase 4.6**

The complete approved security contract must be verified for every supported
deployment mode. Security acceptance combines deterministic configuration and
API tests with deployment-specific frontend, desktop, and Docker checks.

### Required acceptance matrix

| Deployment mode | Scenario | Authentication expectation | Configuration-write expectation |
|---|---|---|---|
| Desktop | Production, loopback | Token always required except `/health` | Non-secret settings persist; Electron manages Jira credentials using `safeStorage` |
| Local browser | `dev` or `test`, loopback, no configured token | Anonymous access allowed | Non-secret settings persist; durable Jira-token writes are rejected |
| Local browser | `dev` or `test`, loopback, configured token | Token required | Non-Electron write restrictions apply |
| Local browser | Production, loopback | Token required | Non-Electron write restrictions apply |
| Local browser | Any non-loopback binding | Token required | Non-Electron write restrictions apply |
| Docker | Every supported configuration | Token required | Secrets come from mounted files or the environment; durable token writes are rejected |

### Authentication and startup coverage

Automated tests must verify that:

- `/health` is the only unauthenticated route and contains no sensitive
  information;
- missing, malformed, and incorrect tokens return `401`;
- a correct token authorizes protected reads and privileged operations;
- authentication happens before request-body validation or business logic;
- query parameters, cookies, and request bodies cannot authenticate requests;
- token comparison uses the approved constant-time validation;
- authentication failures use a generic structured response with
  `Cache-Control: no-store`;
- configuring a token in optional local development mode protects every
  non-health endpoint;
- empty, unknown, wildcard, and non-loopback bind values cannot bypass
  authentication;
- every FastAPI route belongs to exactly one security class; and
- a newly added unclassified route fails the route-inventory test.

When a required token is missing, startup tests must prove failure before
database migration, scheduler startup, API readiness, and desktop workspace
loading. The error identifies the invalid setting without including any token
or credential value.

### Configuration-write coverage

For every applicable deployment mode, automated tests must verify that:

- non-secret Jira settings are validated and written atomically;
- configuration responses return only configured/not-configured indicators;
- Jira and LighthousePM API tokens never appear in responses, errors, logs, or
  persisted application configuration;
- a non-Electron `PUT /config/jira` request that attempts durable Jira-token
  persistence returns `400` with an actionable, non-sensitive explanation;
- `POST /config/jira/test` may use a candidate token for that request but does
  not persist it;
- an invalid or failed connection test leaves existing configuration
  unchanged;
- desktop Jira-token changes continue through Electron `safeStorage`;
- desktop restart retains the encrypted Jira credential without exposing it
  to the renderer; and
- browser bearer tokens use only the approved session-lifetime storage and
  never `localStorage`, IndexedDB, URLs, service-worker caches, or frontend
  build variables.

### Secret-source coverage

Tests must cover direct environment values; valid `*_FILE` sources; missing,
empty, oversized, unreadable, and non-regular secret files; conflicting direct
and file settings; removal of one trailing line ending without otherwise
changing the secret; errors that name the setting without revealing its value;
and Docker secret declarations that contain no committed secret values.

### Docker acceptance

Always-run checks verify the loopback-only backend host port, absence of a
PostgreSQL host port in the base Compose file, the loopback-only optional
PostgreSQL override, explicit Docker mode and container bind address, and
successful `docker compose config` with isolated test secret files.

A container-based authentication smoke test is required in CI and release
verification when Docker is available. It starts an isolated Compose project,
verifies health and authenticated access, verifies rejection of persistent
configuration secrets, and removes its disposable containers, volumes, and
test credentials.

### Regression and isolation requirements

Phase 4 verification requires backend unit and API integration tests, the full
backend regression suite, frontend authentication and storage tests plus a
production build, desktop authentication/proxy/`safeStorage` tests, Docker
configuration and runtime acceptance, and the documentation-contract
safeguards.

Tests use temporary SQLite files, disposable PostgreSQL data, mock Jira access,
and synthetic credentials. They must never access developer or production
data. The acceptance matrix is the authoritative set of supported mode,
environment, and binding combinations; changing that set requires updating the
matrix and its tests together.

This testing contract changes security assurance only. It does not change
metric formulas, signals, thresholds, availability, or output meaning, so the
runtime `ruleset_version` remains `2`.

## Application Response-Assembly Boundaries

Status: **Approved — Phase 5.1**

Release-metric and sprint response assembly belongs to focused application
services, not FastAPI route modules. These services coordinate repositories and
the existing analytics, availability, comparison, recommendation, confidence,
and driver services and return the established Pydantic response models.

API routes retain only HTTP concerns: FastAPI parameter and dependency
declarations, one application-service call, and explicit translation of
defined service outcomes into HTTP responses. Metric calculation remains in
`analytics_service`; availability decisions remain in
`metric_availability_service`; comparison logic remains in
`snapshot_comparison_service`. Response-assembly services must not duplicate
those rules.

Time-dependent assembly receives an explicit current time so snapshot age and
sprint-scope interpretation are reproducible in focused tests. The extraction
must preserve endpoint paths, schemas, status codes, error messages, field
values, ordering, empty and partial behavior, and historical ruleset handling.
No generic response-builder framework or base-service hierarchy is required.

Focused service tests cover empty, current, partial, legacy, and cross-ruleset
snapshots. API contract tests remain responsible for proving that moving the
assembly boundary does not alter public behavior.

## Reporting Pipeline Boundaries

Status: **Approved — Phase 5.2**

Reporting is one deterministic pipeline with six explicit responsibilities:

1. Immutable document models describe report documents, sections, charts,
   images, and visual themes without database access or rendering behavior.
2. Data preparation loads releases, sprints, snapshots, signals,
   recommendations, comparisons, and stored availability and produces prepared
   report data without layout or PDF operations.
3. Release, sprint, overview, and documentation templates transform prepared
   data into document models and do not query repositories.
4. Chart rendering owns chart scaling, raster drawing, and RGB image
   generation.
5. PDF rendering owns pagination, fonts, tables, image embedding, escaping, and
   deterministic PDF serialization.
6. A small reporting facade coordinates data preparation, template selection,
   and PDF rendering for the existing API routes.

The current chart and PDF implementations remain unless a separate approved
decision replaces them. This phase is a responsibility split, not a rendering
library migration or a generic document framework. `generated_at` is passed
explicitly through the pipeline. Stored availability remains authoritative for
historical reports.

The split preserves report endpoints, filenames, content types, report depths,
required sections, explanations, and error behavior. Each extracted boundary
has focused tests, and release, sprint, overview, and documentation PDF API
tests run after every extraction step.

## Frontend Page and Container Boundaries

Status: **Approved — Phase 5.3**

`App.tsx` is the application shell. It owns authentication, top-level
navigation, active project and release context, and page selection. About
content, release workspace loading, tab configuration, navigation rendering,
and page-specific overview, metrics, charts, issues, sprint, report, and
settings behavior belong in focused modules or containers.

Sprint functionality separates one data container from presentational sprint
selection, summary, health, ticket-situation, delivery-confidence, metric,
evidence, chart, comparison, history, and reporting components. Intelligence
and report pages share sprint data ownership and must not issue duplicate API
requests. API access remains in page or container hooks, not presentational
components. Pure metric evaluation and formatting helpers remain separately
testable.

The extraction preserves project scoping, selection, refresh and recomputation
behavior, request cancellation, stale-response protection, loading and error
states, expansion defaults, and issue focus. It does not add React Router, a
global state library, or a generic component framework. Metric metadata is not
re-centralized during this extraction; Phase 5.4 owns that decision.

Frontend assertions and the production build run after each extraction stage.
Desktop navigation and rendering are verified after both large containers are
decomposed.

## Authoritative Metric Catalog

Status: **Approved — Phase 5.4**

`PRODUCT_RULES.md` remains the normative authority for product behavior. One
machine-readable backend metric catalog is the implementation authority for
mechanical release and sprint metric metadata. It must not introduce a formula,
threshold, availability meaning, or historical interpretation absent from the
approved product rules.

Each catalog entry contains its stable key and scope, label, concise
description, category, unit, formatting rule, display order, thresholds and
severity meaning, availability and evidence metadata, API field name,
historical-series support, signal/confidence/chart/report participation, and
applicable ruleset version.

The backend uses catalog selections instead of separate metric-name lists and
uses catalog thresholds, labels, ordering, units, and evidence mappings in API,
signal, report, and chart metadata. Metric formulas remain explicit in
`analytics_service`; signal evaluation remains explicit in `signal_service`;
dynamic availability remains explicit in `metric_availability_service`. The
catalog is not a generic metric or rules engine.

`GET /metadata/metrics` is the protected-read API for the current catalog. It
returns deterministic release and sprint definitions plus catalog and ruleset
versions and contains no credentials or deployment configuration. It follows
the existing bearer-token rules and belongs to the Phase 4 route-security
inventory. The frontend obtains shared labels, descriptions, units, ordering,
thresholds, and availability presentation metadata from this API instead of
maintaining competing maps.

Current catalog metadata must never reinterpret immutable historical results.
Historical responses and reports continue to use stored values, provenance,
thresholds, availability, and ruleset identity. A behavior change first updates
the approved product rules, then the catalog and implementation in the same
change, and increments `ruleset_version` when output meaning changes.

Contract tests require exactly one catalog entry for every API metric, reject
stale and duplicate entries, verify all threshold consumers and public metadata
against the catalog, and keep frontend and report presentation synchronized.

## Phase 5 Documentation Responsibilities

Status: **Approved — Phase 5.5**

Phase 5 retains the document ownership and precedence rules approved in Phase
1.1 and updates each maintained document only within its responsibility:

- `README.md` describes the implemented service, reporting, frontend, metric
  catalog, metadata API, development, and verification architecture.
- `HELPER.md` remains the practical authenticated API reference and removes
  stale limitations or operations.
- `UNIT_TEST_DOCS.md` documents durable coverage areas, focused and full
  commands, and PostgreSQL, Docker, Electron, and packaged-test prerequisites;
  it does not preserve brittle hardcoded test counts.
- `ABOUT.md` retains user-facing interpretation and approved Release Outlook
  language while shared labels, thresholds, units, and availability summaries
  remain synchronized with the catalog.
- `AGENTS.md` retains deterministic, single-service, thin-route, and simplicity
  constraints and adds the approved response-assembly, reporting, catalog, and
  frontend boundaries.

Documents link to, generate, or contract-check mechanical metadata instead of
copying competing definitions. Documentation is updated with the implementation
point that changes it. Final safeguards identify stale endpoints, metric keys,
thresholds, terminology, migration heads, and verification commands. A
documentation-only change cannot silently change product behavior or
`ruleset_version`.

## OpenAPI and Endpoint-Documentation Contract

Status: **Approved — Phase 5.6**

FastAPI OpenAPI is authoritative for the mechanical application endpoint
contract. Each application operation has a stable unique operation ID, an
explicit tag and concise summary, declared parameters and response model, and
documented success and relevant error responses. Protected operations declare
bearer authentication in OpenAPI; `GET /health` is the only public application
operation. Runtime authentication remains centrally enforced by the Phase 4
middleware rather than duplicated as a second dependency path.

Contract tests compare OpenAPI, the centralized FastAPI route inventory,
`README.md`, and `HELPER.md`. Every supported method and path appears exactly
once in each maintained endpoint inventory, path parameter names agree with
OpenAPI, and missing, stale, duplicate, or malformed entries fail with an exact
diagnostic. Built-in `/docs`, `/redoc`, and `/openapi.json` routes remain
protected but are excluded from the application-operation inventory. Automatic
`HEAD` and `OPTIONS` operations are excluded unless deliberately documented.

`HELPER.md` retains human-authored purpose, authentication, parameter,
empty/partial/error, and operational-use guidance. OpenAPI and the metric
catalog supply mechanical endpoint and metric metadata; contract tests do not
attempt subjective prose generation.

An explicit command may export current OpenAPI JSON for external tooling, but a
generated `openapi.json` file is not committed. This assurance contract does
not change endpoint behavior, authentication enforcement, metric meaning, or
the runtime `ruleset_version`, which remains `2`.

## Continuous-Integration Execution Contract

Status: **Approved — Phase 6.1**

GitHub Actions is the repository's continuous-integration provider. CI runs for
pull requests, pushes to the main branch, and manual dispatches. Workflows use
least-privilege read-only repository permissions and cancel superseded runs for
the same branch or pull request.

The pipeline exposes independently visible jobs for backend quality and tests,
PostgreSQL integration, frontend tests and production build, and desktop
validation. Stable job names form the merge-readiness contract: every required
job must pass before a change is considered ready to merge.

Dependency installation is locked and reproducible. Python jobs install from
explicitly maintained requirement files, while frontend and desktop jobs use
`npm ci`. Backend compatibility is checked with Python 3.11, the declared
minimum version. PostgreSQL integration uses PostgreSQL 14, the minimum
supported database version. Frontend and desktop jobs use Node.js 22. Desktop
packaged-backend validation runs on Windows because the distributed backend and
Electron application target Windows. It validates the packaged backend rather
than producing the complete Electron installer; release packaging remains a
separate release process.

Every CI command must also remain runnable locally and documented. CI must not
depend on developer credentials, Jira access, production secrets, or persistent
external services. Test fixtures and generated contract snapshots must be
deterministic.

## Backend Quality and Migration Controls

Status: **Approved — Phase 6.2**

The backend CI job runs on Ubuntu with Python 3.11 and installs the backend
package plus its explicitly maintained development dependencies. The general
backend test command excludes tests marked `postgres`, which run under the
dedicated Phase 6.3 database contract, and tests marked `docker`, which require
an isolated Docker runtime. Static Docker security tests remain part of the
general backend suite because they require no external service.

Ruff checks all maintained backend Python under `app`, `tests`, and `alembic`,
plus `desktop_entry.py` and `seed.py`. MyPy checks `app`, matching the existing
application boundary. Phase 6 does not impose an unrelated strict-mode
conversion, but every error reported within the configured boundary fails CI.

Migration checks enforce exactly one loadable Alembic head and an unbroken
revision graph. Deterministic SQLite coverage verifies clean migration to head,
upgrade from every supported versioned revision and registered unversioned
legacy schema, idempotence, data preservation, backup behavior, invalid-state
handling, and maintained documentation references to the current head.
PostgreSQL migration execution remains in Phase 6.3 so database-infrastructure
failures are independently visible.

Local Makefile targets and CI use the same commands. Any backend test, Ruff,
MyPy, or migration-check failure blocks the backend job. No coverage-percentage
threshold is introduced without a separate approved product decision.

## PostgreSQL Integration Gate

Status: **Approved — Phase 6.3**

A dedicated Ubuntu CI job runs against an ephemeral PostgreSQL 14 service with
synthetic credentials and a service health check. It sets
`MIGRATION_TEST_POSTGRES_ADMIN_URL` to the administrative `postgres` database
and runs every test marked `postgres`, so newly marked PostgreSQL tests enter
the gate automatically.

CI enables an explicit required-test flag. A missing administrative URL,
unavailable service, skipped required test, or uncollected PostgreSQL suite is a
failure rather than a successful no-op. The job uses no repository, Jira,
developer, or production credential and attaches no persistent database volume.

Each test creates a uniquely named disposable database. Cleanup may remove only
the `lighthouse_migration_*` and `lighthouse_startup_*` namespaces and must
refuse any other database name. The normal LighthousePM application database is
never a test target.

The gate verifies every supported versioned PostgreSQL migration to the current
head, preservation of existing data, idempotent repeat migration and startup,
clean application startup, migration before readiness for an existing database,
authenticated health and representative API responses, and structured
empty-dataset responses. The equivalent local command and prerequisites remain
documented in `UNIT_TEST_DOCS.md`.

Docker Compose security acceptance remains separate. This gate tests the
backend directly against PostgreSQL and does not build application containers.

## Frontend Assertions and Production-Build Gate

Status: **Approved — Phase 6.4**

A dedicated Ubuntu CI job uses Node.js 22 and installs the committed frontend
lockfile with `npm ci`. Separate steps run the deterministic logic assertions
and the TypeScript plus Vite production build. Any dependency-installation,
TypeScript, assertion, or bundling failure blocks the job.

The assertion runner must fail when it discovers no source tests, produces no
executable compiled tests, or encounters a failing assertion. Existing coverage
continues to protect authentication, workspace state, release and project
selection, navigation, Jira configuration, metric availability, confidence,
charts, recommendations, and metric-catalog compatibility. It remains locally
isolated and requires neither a backend process nor API or Jira credentials.

Build warnings remain visible but are not all promoted to failures. In
particular, the existing bundle-size warning does not silently create a new
bundle policy in this point. Generated `.tmp-tests`, TypeScript build metadata,
and `dist` output remain untracked; Phase 6.9 owns their ignore and cleanup
rules.

Phase 6.6 adds component-rendering and accessibility coverage. Once present,
the frontend provides one documented local entry point that runs both the
logic-assertion and component suites. Commands and prerequisites remain
documented in `UNIT_TEST_DOCS.md`.

## Desktop Lint and Packaged-Backend Smoke Gate

Status: **Approved — Phase 6.5**

The desktop CI job runs on Windows with Node.js 22 and Python 3.11. It installs
the desktop lockfile with `npm ci` and installs the maintained backend runtime
and development dependencies, including PyInstaller. `npm run lint` checks the
Electron main and preload files, storage and operation-control modules, desktop
build and verification scripts, and Electron Forge configuration.

The job builds the real Windows backend executable with
`npm run build:backend`. A focused packaged-backend smoke command verifies the
expected executable, starts it on a dynamically selected loopback port with a
temporary SQLite database and synthetic API token, and waits for health within
a bounded timeout. It then verifies that an unauthenticated protected request
returns `401` and an authenticated releases request returns a structured empty
response. This proves that the packaged executable contains the application,
migrations, API schemas, authentication middleware, and required runtime
dependencies.

The smoke command captures useful process diagnostics without printing the
synthetic token, terminates the packaged process, and removes its temporary
data. Build failure, missing output, early process exit, readiness timeout,
incorrect authentication behavior, malformed API output, or failed cleanup
fails the job. The same command remains documented for local execution.

This gate does not build the React frontend, Electron package, ZIP, or
installer. Complete Electron packaging, release verification, signing, and
interactive clean-machine acceptance remain separate release controls.

## Component-Level Frontend Behavior and Accessibility Tests

Status: **Approved — Phase 6.6**

The frontend adds a focused React component-test layer using Vitest, React
Testing Library, `user-event`, `jest-dom`, JSDOM, and automated Axe checks.
Existing compiled Node assertions remain separate. `test:assertions` runs the
existing suite, `test:components` runs component tests under a dedicated file
convention, and `test` runs both as the single local and CI entry point.

Component coverage includes authentication, release-list, release-detail,
sprint-list, and sprint-detail loading behavior; release, sprint, metric, and
report empty states; invalid-token and API-request errors; and removal of stale
loading indicators and unrelated stale data after failure.

Project-switching tests verify that saving a different Jira project clears the
previous project's releases, selection, metrics, charts, signal, and sprint
state; loads and selects the new project independently; and prevents a late
response from the previous project from repopulating the active workspace.

Accessibility tests verify accessible roles, names, labels, disabled states,
form and validation-message associations, dialog labeling and close behavior,
keyboard operation, and no automated Axe violations in representative loading,
empty, error, and populated states. Automated rules are a regression aid and
are not represented as complete accessibility certification.

Tests mock the API-client boundary and make no network request. They prefer
accessible role and label queries over CSS selectors, assert both present and
prohibited stale content, avoid broad DOM snapshots and implementation-state
assertions, and reset mocks and rendered DOM between cases. Only small focused
testability seams may be added; no generic frontend abstraction framework is
introduced.

## Desktop IPC, Security, and Lifecycle Tests

Status: **Approved — Phase 6.7**

Existing desktop storage, recovery, shutdown, startup, transaction, rollback,
backup, restore, Clear Data, Factory Reset, and interrupted-journal tests remain
required. Phase 6 adds only coverage and safeguards missing from those suites.

The preload exposes only the approved frozen `lighthouseDesktop` API and no
generic Electron, process, filesystem, send, or invoke capability. Exposed
channel names exactly match registered main-process handlers. Every IPC request
validates that its sender belongs to the active LighthousePM renderer; foreign
origins, detached frames, and unavailable renderer state fail closed. Storage
operations accept no renderer-supplied filesystem paths, Jira-token, PDF-save,
and external-link payloads are validated before side effects, and mutating
storage requests retain the exclusive operation lock.

Executable security tests enforce `contextIsolation: true`,
`nodeIntegration: false`, `sandbox: true`, `webSecurity: true`, and
`allowRunningInsecureContent: false`. Permission checks, permission requests,
and device permissions are denied. Navigation outside the active renderer,
new windows, and webviews are blocked. Only valid HTTPS links may be delegated
to the operating system. The local API token may be attached only to the exact
development renderer origin's `/api` requests and never to another origin.
Startup and backend-error documents escape untrusted details.

Lifecycle coverage verifies that pre-readiness failure keeps the workspace
closed; unexpected backend exit shows the error boundary and log location;
intentional shutdown does not report an unexpected exit; a second instance
restores and focuses the existing window; application shutdown waits for
confirmed backend termination; recovery completes before ordinary backend
startup; and recovery, migration, and configuration failures remain
fail-closed.

Tests prefer executable Node behavior with mocked Electron boundaries and small
pure policy helpers. Limited source-contract assertions remain only for
immutable Electron wiring. Normal CI does not launch the Electron GUI or add a
desktop testing framework. `test:node` runs the Node suite, `npm test` remains
the local aggregate, and empty test discovery is a failure. Windows CI runs the
Node suite after lint and before the packaged-backend smoke. GUI, installer,
upgrade, and clean-machine behavior remains release acceptance.

## Critical API Payload Snapshots

Status: **Approved — Phase 6.8**

Committed human-readable JSON contracts protect representative paginated and
project-scoped release data; populated and incomplete-evidence release metrics;
stored release signals with reasons, ruleset, provenance, and availability;
release snapshot comparison; sprint collection and current-sprint selection;
sprint metrics with complete, partial, and inconclusive story-point coverage
and repeated reopen-event evidence; sprint snapshot comparison; redacted Jira
configuration; successful Jira synchronization; and standard `401`, `404`,
`409`, and `422` error payloads.

Snapshots compare the complete serialized payload, including names, nesting,
nullability, ordering, reasons, and evidence. Fixtures use fixed identifiers,
dates, timestamps, seeded data, and frozen clock sources where required.
Nondeterministic fields are not broadly removed. API tokens, Jira credentials,
database URLs, local paths, and other secrets must never enter a snapshot.

OpenAPI remains authoritative for endpoint mechanics and schemas, semantic
tests remain authoritative for formulas and rules, and `PRODUCT_RULES.md`
remains the product-rule authority. PDF bytes, generated OpenAPI JSON, and the
complete metric catalog are not duplicated as snapshots because focused
contracts already protect them.

A manifest test rejects missing, duplicate, and orphaned snapshot files.
Ordinary tests and CI compare snapshots read-only and never rewrite them. One
explicit local command regenerates the contracts from deterministic fixtures,
must produce a reviewable diff, and fails for nondeterministic output. An
intentional change requires review of schemas, frontend consumers, maintained
documentation, and `ruleset_version` whenever metric meaning changes.

## Line Endings and Repository Hygiene

Status: **Approved — Phase 6.9**

`.gitattributes` defines LF for source code, Markdown, configuration, YAML,
JSON, lockfiles, shell scripts, and web assets; CRLF only for Windows command,
batch, and PowerShell scripts; and explicit binary treatment for images, icons,
PDFs, archives, executables, and databases. It performs no encoding conversion
or generated-content filtering. Tracked files are renormalized against this
policy and checked with `git diff --check`.

The repository removes `6.0`, tracked log files, all generated
`frontend/.tmp-tests` output, frontend TypeScript build metadata, the generated
`frontend/vite.config.js` and `frontend/vite.config.d.ts` duplicates of
`frontend/vite.config.ts`, and the known malformed `WorkingDirectory`/`PassThru`
filename and its untracked variant. `.gitignore` covers `*.log`,
`*.tsbuildinfo`, `frontend/.tmp-tests/`, `frontend/vite.config.js`,
`frontend/vite.config.d.ts`, and `6.0`. Malformed filename patterns are not
ignored: future occurrences remain visible and fail the hygiene check.

A deterministic safeguard rejects tracked generated-test output, logs,
TypeScript build metadata, generated Vite configuration duplicates, `6.0`,
known accidental command fragments, a missing line-ending policy, and
verification commands that unexpectedly modify tracked generated content.

History retains two isolated changes: a line-ending-only change containing
`.gitattributes` and renormalization, followed by a dedicated hygiene change
containing `.gitignore`, artifact removal, and the safeguard. Renormalization
must wait for a safe committed functional baseline. Existing work is never
reset, stashed, discarded, or mixed with line-ending noise. The index is
inspected and explicit confirmation requested before either commit is created.

## Explicit and Reproducible Dependencies

Status: **Approved — Phase 6.10**

`backend/pyproject.toml` is the canonical direct-dependency declaration. It
explicitly declares FastAPI, Starlette, Pydantic, pydantic-settings, SQLAlchemy,
Alembic, the psycopg binary distribution, HTTPX, APScheduler, Uvicorn, and
python-dotenv as runtime requirements. A single `dev` optional-dependency group
declares pytest, pytest-asyncio, Ruff, MyPy, PyInstaller, and the selected Python
lock-generation tool. Alembic is not duplicated as a development-only
requirement. LighthousePM never relies on a transitive installation for a
package it imports directly or loads as its configured database driver.

Exact platform-appropriate lock files are generated from this canonical
metadata rather than from a competing handwritten dependency list. Maintained
locks cover Linux runtime, Linux CI/development, and Windows CI/packaged-backend
installation. Regeneration is an explicit documented command, and CI rejects a
regenerated diff. Jobs install the applicable lock, install the project with
`--no-deps`, and run `pip check`. Docker builds use the Linux runtime lock
instead of resolving open ranges during each image build.

Frontend runtime dependencies remain React, React DOM, and Recharts. TypeScript,
Vite, React types, the React Vite plugin, and every Phase 6.6 testing package
are explicit development dependencies. Desktop explicitly declares Electron,
Electron Forge, each configured maker, and every directly invoked build
utility. Electron remains a development dependency because it supplies the
packaged runtime API, and no desktop test framework is added. Npm lockfiles are
updated only through npm; CI uses `npm ci` and `npm ls --depth=0`.

A deterministic inventory check maps imported module names to distribution
names and rejects undeclared third-party production or test/build imports.
Standard-library, Node built-in, local, generated, and internal type-only
imports are excluded explicitly. Fresh CI environments must pass without
globally installed packages. Phase 6 performs no unrelated opportunistic
dependency upgrade. Installation, lock regeneration, and validation remain
documented in `README.md` and `UNIT_TEST_DOCS.md`.

## Phase 6 Verification and Completion Gate

Status: **Approved — Phase 6.11**

The stable required CI jobs are `backend-quality`, `postgres-integration`,
`frontend`, `desktop`, and `docker-security`. The Docker job preserves the
already approved Phase 4.6 acceptance requirement: on an Ubuntu runner with
Docker available, it sets `LIGHTHOUSE_REQUIRE_DOCKER_SECURITY=1`, uses only
synthetic secret files, builds an isolated Compose project, verifies health,
authentication, configuration-secret rejection, and network isolation, and
removes disposable containers, volumes, images, and credentials. Required
Docker acceptance fails rather than skips.

Phase 6 is complete only when backend non-external tests, whole-backend Ruff,
application MyPy, SQLite migration integrity, required PostgreSQL acceptance,
frontend logic and component tests, TypeScript and the production build,
desktop lint and Node tests, the real packaged Windows backend smoke, Docker
runtime security acceptance, API payload snapshots, dependency inventory and
locks, `pip check`, `npm ls`, repository hygiene, and line-ending checks pass.
Each required suite fails on empty or skipped collection where applicable.
Verification commands must leave tracked generated content unchanged.

`README.md`, `UNIT_TEST_DOCS.md`, and relevant `AGENTS.md` delivery instructions
must match the implemented commands. No gate depends on Jira, production,
developer, or repository secrets. Ordinary CI does not build a complete
Electron installer or replace interactive clean-machine acceptance. Stable job
names are provided for owner-managed branch protection, but repository-external
GitHub settings are not changed automatically.

Final reporting separates locally passed gates, environment-dependent gates,
and CI-only results that have not actually run. Existing warnings, including
the frontend bundle-size warning, remain visible. Delivery-control and IPC
security changes do not alter metric meaning, so `ruleset_version` remains `2`.

## Jira Incremental Sync State

Status: **Approved — Phase 7.1**

LighthousePM persists Jira freshness from Jira's own issue `updated` timestamp
so synchronization can become incremental without making local clock time part
of metric meaning. The stored Jira update timestamp is issue data: it records
the latest authoritative modification time observed from Jira for that issue.
It is separate from local ingestion time, metric snapshot time, and release or
sprint ruleset provenance.

Each Jira project sync may persist a last-success marker or cursor derived from
the Jira update timestamps successfully processed for that project. A successful
incremental sync may advance this marker only after the sync transaction has
durably stored all accepted issue data and changelog data needed by the current
rules. Failed, cancelled, rejected, or partially persisted sync attempts must
not advance the marker.

First sync and explicit full sync remain supported. When no marker exists, when
the marker is invalid, or when incremental Jira queries fail in a way that
prevents trustworthy freshness filtering, the service falls back to the
existing full-sync behavior and reports the fallback reason. Incremental sync
does not change metric formulas, thresholds, availability rules, evidence
requirements, snapshot interpretation, or `ruleset_version`.

Tests must cover first sync with no marker, successful marker advancement,
unchanged Jira issues, changed Jira issues, failed sync preserving the previous
marker, and fallback to full sync when incremental freshness cannot be trusted.

## Jira Unchanged Issue Fetch Avoidance

Status: **Approved — Phase 7.2**

Incremental sync may use the persisted per-project Jira update cursor to avoid
refetching full issue details and changelogs for issues whose Jira `updated`
timestamp is not newer than the last successful project cursor. The skip
decision must be based only on Jira's authoritative `updated` timestamp and the
persisted cursor from the last successful sync.

Skipping unchanged issue details is allowed only when the issue already exists
locally and its stored Jira update timestamp is present. If the issue is missing
locally, has no stored Jira update timestamp, has incomplete changelog data, or
belongs to a project without a trusted cursor, the service must fetch and
persist the issue through the full existing path.

Skipped issues count as sync activity but do not alter stored issue fields,
changelog rows, metric formulas, signal thresholds, evidence requirements,
ruleset version, or historical snapshot interpretation. Sync results must
expose how many issue details and changelogs were skipped because Jira reported
them as unchanged.

If Jira incremental search fails or returns data that cannot be trusted for
freshness filtering, sync falls back to full fetch behavior and reports the
fallback reason. The project cursor advances only after the successful
transaction, using the max accepted Jira update timestamp from fetched or
trusted unchanged issue summaries.

## Jira Sync Visibility

Status: **Approved — Phase 7.3**

LighthousePM exposes per-project sync visibility so users can tell whether Jira
data is fresh, stale, currently syncing, or failed. Visibility is operational
state only: it does not change metric formulas, thresholds, evidence rules,
snapshot interpretation, or `ruleset_version`.

For each configured Jira project, the backend records and exposes:

1. project key;
2. current sync status: `idle`, `running`, `succeeded`, or `failed`;
3. last successful sync time;
4. last successful Jira update cursor;
5. last failed sync time;
6. sanitized failure summary; and
7. issue totals for the latest completed sync, including fetched, inserted,
   updated, unchanged-skipped, failed-skipped, changelog fetched, inserted,
   duplicate-skipped, and unchanged-skipped counts.

A running sync may expose coarse progress such as current phase and processed
issue count. Progress is best-effort and must never be used as metric evidence.
If process restart loses in-memory running progress, the backend must report a
clear non-running state from persisted last-success and last-failure markers
rather than pretending the old sync is still active.

The sync endpoint response and status endpoint must use structured fields. The
frontend may display these markers near project sync controls, but must not
infer freshness from local browser time alone.

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

## Documentation Drift Safeguards

Status: **Approved — Phase 1.5**

The existing backend pytest suite must enforce the following documentation
contracts without adding production behavior or a separate validation
framework:

1. The method-and-path inventory under `README.md` REST API headings must
   exactly match the public application routes registered by FastAPI. Built-in
   OpenAPI and documentation routes are excluded.
2. The current single Alembic head must be stated in both `README.md` and
   `desktop/README.md`. Adding or changing the head requires updating both
   documents in the same change.
3. Maintained user and technical documentation must not restore the retired
   labels `Release Prediction`, `Predicted outcome`, or `Likely outcome`.
4. `README.md`, `ABOUT.md`, and `desktop/README.md` must retain the canonical
   `Release Outlook` term.

The checks must read repository files without modifying them, report the
specific missing, stale, or prohibited contract when they fail, and run as
ordinary focused pytest tests. They intentionally protect exact public
contracts rather than attempting subjective prose validation.

## Phase 0 Decision Register

| Point | Decision | Status |
|---|---|---|
| 0.1 | Use `PRODUCT_RULES.md` as the canonical product-rule catalog | Approved |
| 0.2 | Use the worse of hard-rule severity and weighted confidence-band severity | Approved |
| 0.3 | Return a partial score from 50% coverage; below 50% is inconclusive | Approved |
| 0.4 | Use Jira issue age and current uninterrupted risk age as separate facts | Approved |
| 0.5 | Replace prediction claims with a deterministic current Release Outlook | Approved |
| 0.6 | Use immutable snapshots and a monotonically increasing integer ruleset version | Approved |

## Phase 1 Decision Register

Phase 1 aligns every maintained document and public contract with the approved
Phase 0 behavior before new product features are introduced.

| Point | Decision | Status |
|---|---|---|
| 1.1 | Assign one explicit responsibility to each maintained document and define conflict precedence | Approved |
| 1.2 | Reconcile the technical overview and API contract in `README.md` with the current implementation | Approved |
| 1.3 | Replace unsupported predictive user language in `ABOUT.md` with deterministic Release Outlook language | Approved |
| 1.4 | Align `desktop/README.md` with automatic migration, backup, restart, and recovery behavior | Approved |
| 1.5 | Add deterministic safeguards against future documentation and contract drift | Approved |

## Phase 2 Decision Register

Phase 2 approves and hardens the remaining metric contracts before their
formulas or public meaning are changed under a new ruleset version.

| Point | Decision | Status |
|---|---|---|
| 2.1 | Make Jira value classifications configurable, reproducible, and comparison-safe | Approved |
| 2.2 | Define complete availability and evidence contracts for release scope and risk metrics | Approved |
| 2.3 | Use a bounded, evidence-backed seven-day scope-churn contract | Approved |
| 2.4 | Define valid cycle-time pairs and an eligible reopen-event-rate denominator | Approved |
| 2.5 | Clarify sprint scope and unfinished-work semantics without breaking the API | Approved |
| 2.5.4 | Make workload distribution authoritative, coverage-aware, and reproducible | Approved |

## Phase 3 Decision Register

Phase 3 establishes safe schema and desktop upgrades before security and
architectural restructuring work begins.

| Point | Decision | Status |
|---|---|---|
| 3.1 | Use Alembic as the only runtime schema authority for PostgreSQL and SQLite | Approved |
| 3.2 | Gate desktop backend readiness and workspace loading on successful migration | Approved |
| 3.3 | Test upgrades from every supported versioned and unversioned schema source | Approved |
| 3.4 | Verify clean-install and existing-database behavior through application and desktop startup | Approved |
| 3.5 | Atomically publish consistent SQLite migration backups before migration begins | Approved |
| 3.6 | Validate backup format, integrity, and schema compatibility before reuse or restore | Approved |
| 3.7 | Make desktop storage operations recoverable and test upgrade, backup, restore, reset, and rollback lifecycles | Approved |

## Phase 4 Decision Register

Phase 4 secures every supported deployment mode before architectural
restructuring work begins.

| Point | Decision | Status |
|---|---|---|
| 4.1 | Define explicit security boundaries for desktop-only, local-browser, and Docker deployments | Approved |
| 4.2 | Require API authentication in production, on non-loopback bindings, and in desktop and Docker modes | Approved |
| 4.3 | Bind Docker API access to host loopback and keep PostgreSQL private by default | Approved |
| 4.4 | Classify every route and explicitly protect configuration, administration, sync, and recomputation operations | Approved |
| 4.5 | Keep non-Electron secrets in operator-controlled providers and reject application-managed durable token writes | Approved |
| 4.6 | Verify authentication and configuration-write behavior across every supported deployment mode | Approved |

## Phase 5 Decision Register

Phase 5 restores architecture and documentation clarity without changing the
approved single-service product model or introducing a generic abstraction
framework.

| Point | Decision | Status |
|---|---|---|
| 5.1 | Move release-metric and sprint response assembly into focused application services | Approved |
| 5.2 | Split reporting into document models, data preparation, templates, chart rendering, PDF rendering, and a small facade | Approved |
| 5.3 | Split `App.tsx` and `SprintsPanel.tsx` by page and container responsibility | Approved |
| 5.4 | Use one metric catalog for shared metadata while retaining `PRODUCT_RULES.md` as the normative product authority | Approved |
| 5.5 | Reconcile maintained technical, API, test, user, and agent documentation with the implemented architecture | Approved |
| 5.6 | Make OpenAPI authoritative for endpoint mechanics and enforce documentation synchronization with contract tests | Approved |

## Phase 6 Decision Register

Phase 6 strengthens deterministic delivery controls without changing product
behavior or the approved single-service architecture.

| Point | Decision | Status |
|---|---|---|
| 6.1 | Use GitHub Actions with reproducible, independently visible backend, PostgreSQL, frontend, and desktop quality gates | Approved |
| 6.2 | Enforce backend tests, whole-backend Ruff checks, application MyPy checks, and deterministic SQLite migration integrity | Approved |
| 6.3 | Require isolated PostgreSQL 14 migration and startup acceptance with fail-closed test collection | Approved |
| 6.4 | Require deterministic frontend assertions, non-empty test collection, TypeScript compilation, and a production Vite build | Approved |
| 6.5 | Require Windows desktop lint plus a bounded authentication and API smoke test of the real PyInstaller backend | Approved |
| 6.6 | Add deterministic component tests for loading, empty, error, project-switching, keyboard, semantic, and automated accessibility behavior | Approved |
| 6.7 | Add gap-based executable IPC sender, Electron security-policy, and application lifecycle tests while retaining existing recovery coverage | Approved |
| 6.8 | Protect representative critical API serialization with deterministic, reviewable, read-only JSON contract snapshots | Approved |
| 6.9 | Normalize line endings and remove generated, logged, metadata, and accidental tracked artifacts through isolated safeguards and commits | Approved |
| 6.10 | Declare every direct backend, frontend, desktop, and test/build dependency and enforce platform-specific reproducible locks | Approved |
| 6.11 | Require complete backend, PostgreSQL, frontend, desktop, Docker, contract, dependency, hygiene, and documentation verification | Approved |

## Phase 7 Decision Register

Phase 7 improves sync performance and user experience after correctness,
security, architecture, and delivery controls are stable. It must not change
metric formulas, ruleset meaning, signal thresholds, or stored historical
interpretation unless a later approved product rule explicitly requires it.

| Point | Decision | Status |
|---|---|---|
| 7.1 | Persist Jira issue update timestamps and use them to support deterministic incremental synchronization | Approved |
| 7.2 | Avoid refetching unchanged Jira issue details and changelogs while preserving reproducible stored data | Approved |
| 7.3 | Add per-project sync progress, last-success markers, and clear failure state visibility | Approved |
| 7.4 | Code-split heavy frontend screens such as reporting, charts, settings, and documentation to reduce the production bundle | Proposed |
| 7.5 | Define snapshot-retention rules only if long-running installations show meaningful storage growth | Proposed |
