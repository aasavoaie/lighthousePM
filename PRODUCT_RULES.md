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
