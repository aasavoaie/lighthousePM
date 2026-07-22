# LighthousePM

## Overview

### What the product does

LighthousePM turns Jira release and sprint activity into deterministic delivery metrics, release readiness signals, and recommended actions. It is built for teams that need a clear view of blockers, quality risk, scope movement, flow health, and confidence trends before release decisions are made.

The product is organized around:

- Release Intelligence: confidence, readiness, critical risks, warnings, tickets, and release-level trend history.
- Sprint Intelligence: progress alignment, active work, blockers, sprint-created bugs, unfinished closed-sprint work, and historical commitment reliability.
- Explainable Signals: every confidence signal is tied to explicit metrics, thresholds, reasons, and risk contribution.
- Operational Evidence: reports preserve the charts, aging detail, comparison data, and ticket context behind each decision.

Metric names, units, formatting, thresholds, and availability boundaries shown by the application come from the versioned metric catalog. This guide explains how to interpret those results; it does not redefine their mechanical rules. `PRODUCT_RULES.md` remains the detailed product authority.

### What the Overview shows

The Overview section is the executive decision view of LighthousePM. It gives a Head of PO, CEO, or Head of PM a single place to understand what the latest stored evidence says about the selected release, what is creating delivery or quality risk, and which actions should be considered first.

Instead of asking leadership to inspect Jira issue by issue, the screen turns release and sprint activity into deterministic evidence. It supports release governance with clear signals: current confidence, trend direction, active risks, the current Release Outlook, recommended actions, and current sprint context.

#### Release Readiness

Release Readiness is the executive release health indicator. It classifies the latest stored release evidence as ready, needing management attention, at serious risk, inconclusive, or not computed.

Should answer the following questions:

- Can we still stand behind this release commitment?
- Is the release healthy enough to continue without intervention?
- What message should leadership use with stakeholders?
- Do we need a go/no-go discussion, scope decision, or escalation?

The score and label are based on computed release data, not manual judgment.

#### Confidence Engine

The Confidence Engine explains what is reducing confidence in the release. It identifies the strongest negative drivers, such as high-severity bugs, scope churn, reopen events per 100 eligible tickets, blockers, or cycle time.

Should answer the following questions:

- What is the biggest reason confidence is dropping?
- Is the problem delivery, quality, flow, scope control, or unresolved risk?
- Which leadership lever is needed: prioritization, scope trade-off, escalation, or team focus?
- Where should management attention go first?

This turns a vague release concern into specific, explainable causes that can be discussed with the team and stakeholders.

#### Confidence Trend

The Confidence Trend shows whether stored release confidence improved, remained stable, or deteriorated across available snapshots. It is historical evidence, not a forecast of the next snapshot or the release outcome.

Should answer the following questions:

- How has confidence changed across the stored snapshots?
- Which recorded metric changes accompanied that movement?
- Does a ruleset boundary prevent a direct comparison?
- Does the current evidence justify a scope, quality, ownership, or date discussion?

The trend also shows the change since the first displayed snapshot when the comparison is valid. Version boundaries remain explicit and incompatible rulesets are not mixed into a derived comparison.

#### Release Outlook

Release Outlook summarizes the latest stored release evidence. It shows the current confidence and final signal, passed and failed release gates, confidence change against the latest available 24-hour baseline, calendar days remaining until the Jira release date, and active hard RED and YELLOW conditions.

Should answer the following questions:

- What does the current release signal say about the release commitment?
- Which release gates are currently passing or failing?
- Has confidence improved or deteriorated against the available 24-hour baseline?
- How many calendar days remain, and which active conditions require attention now?

Release Outlook is not a forecast. It does not estimate a probability, predict future confidence, or claim a chance of meeting the release target. It helps leadership act on the evidence that is currently available.

#### Risk Aging

Risk Aging separates issue age from the current uninterrupted blocker or high-severity-risk age. Risk age begins when the active risk condition can be proven from Jira history; if that start cannot be proven, the age remains unavailable and the risk remains visible.

Should answer the following questions:

- Are serious risks staying open long enough to threaten the release?
- Are old unresolved issues reducing confidence in the delivery plan?
- Which risks need leadership attention because they are not moving?
- Is there still enough time to fix and verify critical work before release?

Aging risks matter because unresolved critical work compresses the time available for validation and increases current delivery risk.

#### Recommended Actions

Recommended Actions lists deterministic actions associated with the active evidence. Each action includes a priority, category, effort level, and rule-defined confidence impact used for ordering. That impact is not a prediction of the score change that will occur after the action.

Should answer the following questions:

- What should the organization consider next in response to the current evidence?
- Which active rule carries the largest configured confidence impact?
- Are we solving the right category of problem: delivery, quality, flow, or risk?
- What should leadership ask the team to focus on now?

The actions are rule-based and deterministic. They are designed to support leadership decision-making without guesswork.

#### Additional Warnings

Additional Warnings lists active risk messages that may not be the largest confidence drivers but still require attention.

Should answer the following questions:

- What secondary risks should leadership keep visible?
- Could any warning signs require executive attention if they remain unresolved?
- What should be included in release governance or stakeholder updates?
- Which risks should be monitored even if they are not the top blocker today?

#### Active Sprint

The Active Sprint card connects release health to the sprint currently in progress. It shows the active sprint, latest sprint snapshot, sprint state, end date, and delivery confidence when available.

Should answer the following questions:

- Is the current sprint supporting the release plan or putting it under pressure?
- Does sprint delivery confidence match the release expectation?
- Do current sprint completion and delivery confidence support the work needed for the release?
- Do sprint risks require scope, priority, or capacity decisions?

### How to read data availability

LighthousePM keeps missing and incomplete evidence visible instead of replacing it with a healthy value:

- **Computed** means the required evidence for that result is complete.
- **Partial** means some confirmed evidence remains, but an incomplete input could affect the result. Depending on the metric, the product returns a confirmed-minimum count, a documented subset score, or no final percentage. The response explains what is excluded or incomplete.
- **Inconclusive** means the available evidence is insufficient for the requested confidence result. It is an availability state, not a fourth risk severity.
- **Not computed** means there is no usable snapshot, scope, denominator, or qualifying evidence for the calculation.
- **Not applicable** means the metric does not apply to the entity's current state, such as unfinished closed-sprint scope for an active sprint.

Always read the status, explanation, and affected Jira keys with the displayed value. A partial count can be a confirmed minimum, while a percentage whose denominator is uncertain is withheld. No missing input is silently replaced with zero, a default story-point value, or another apparently healthy result.

### How leadership should use the Overview

The Overview is designed for release readiness, steering, and go/no-go conversations. A Head of PO, CEO, or Head of PM can use it before leadership updates, release reviews, stakeholder meetings, and escalation discussions.

The recommended flow is:

1. Check Release Readiness to understand the current release state.
2. Review the Confidence Engine to identify the biggest causes of risk.
3. Look at the Confidence Trend and Release Outlook to understand direction and the latest release evidence.
4. Use Risk Aging to identify unresolved critical items that may need escalation.
5. Prioritize work from Recommended Actions.
6. Use Additional Warnings and Active Sprint context to prepare stakeholder updates.

### Why this matters

The Overview turns Jira activity into a leadership decision view. It helps explain not only whether a release is healthy, but why it is healthy or risky, what changed in the stored evidence, and what action should be taken.

This keeps release management focused on evidence, transparent trade-offs, and accountable next steps.

## Releases

The Releases area explains release readiness in two layers: Command Center for current operational decisions, and Reports & Evidence for the historical proof behind those decisions.

### Command Center: Executive Reporting

Executive Reporting creates a consistent release export for governance, stakeholder communication, and release reviews.

Should answer the following questions:

- Can we produce a clear release summary for leadership?
- Is the current release state easy to share outside the delivery team?
- Do we have evidence ready for a go/no-go or steering conversation?

### Command Center: Release Confidence Signal

Release Confidence Signal summarizes readiness, confidence, release gates, critical risks, warnings, risk aging, confidence breakdown, and the biggest confidence drag.

Should answer the following questions:

- Is this release green, yellow, or red for explainable reasons?
- Which gates are blocking readiness?
- What is the single largest risk driver leadership should discuss?
- Are blockers, high-severity bugs, or warnings aging too long?

### Command Center: Metrics

Metrics groups release health into Delivery, Quality, Flow, and Risk so leaders can see the measurable causes behind readiness.

Should answer the following questions:

- Is scope being completed fast enough?
- Is scope churn changing the release commitment?
- Are quality indicators such as high-severity bugs and reopen events per 100 eligible tickets acceptable?
- Are flow or blocker risks delaying release confidence?

### Command Center: Release Controls and Tickets

Release controls and tickets connect the selected release, recomputed snapshots, and issue-level evidence behind the current status.

Should answer the following questions:

- Are we reviewing the right release?
- Were metrics recomputed after the latest Jira changes?
- Which unresolved tickets explain the release status?

### Reports & Evidence: Release Charts

Release Charts preserve historical proof through confidence evolution, risk breakdown, quality gates, readiness, blocker aging, and release comparison.

Should answer the following questions:

- Is confidence improving or deteriorating over time?
- Which risks contribute most to the current confidence score?
- Are quality gates and readiness moving in the right direction?
- How does this release compare with other recent releases?

### Reports & Evidence: Tickets

Tickets provide issue-level evidence behind release metrics and reports, with filters for not-done and completed work.

Should answer the following questions:

- Which unresolved tickets still affect the release decision?
- Which completed tickets support release progress?
- Can leadership trace every signal back to concrete Jira work?

### Release metric definitions

These metrics explain the evidence behind release confidence. They help leadership separate delivery progress, quality risk, flow health, scope movement, and blocking risk before a release decision is made.

#### Metric: Scope completed

Shows the percentage of release scope that is done. This is the simplest delivery-progress signal for the release commitment.

It is ticket-based and does not use story points. If any current release ticket has no status, the percentage is withheld and marked Partial with the affected Jira keys. Empty release scope is Not computed rather than zero.

Should answer the following questions:

- Is enough release scope complete for the planned date?
- Is delivery progress aligned with the business expectation?
- Do we need to reduce scope or increase delivery focus?

#### Metric: Completed tickets

Counts the release tickets already finished. It gives leadership a concrete volume of delivered work behind the completion percentage.

If current release tickets are missing status, the displayed count is a confirmed minimum and is marked Partial. Empty release scope is Not computed.

Should answer the following questions:

- How much work has actually landed?
- Is progress supported by completed Jira items?
- Can we explain release progress with ticket-level evidence?

#### Metric: Scope churn 7d

Measures distinct release scope additions and removals over the seven days ending at the stored snapshot time. The percentage compares tickets with confirmed movement against the observed scope: current release tickets plus tickets with confirmed additions or removals. High churn means the release target is still changing while the team is trying to finish it.

If Jira changelog ingestion is incomplete for any synchronized project ticket, the percentage is shown as unavailable. Confirmed added and removed counts remain visible as partial evidence, together with the Jira keys whose history is incomplete.

Should answer the following questions:

- Is the release commitment stable enough to govern?
- Are new requests or removals changing the delivery promise late?
- Should leadership freeze scope or defer non-critical work?

#### Metric: Scope added 7d

Counts tickets added to the release in the recent scope window. It explains whether churn is caused by new work entering the release.

Should answer the following questions:

- What new work has entered the release recently?
- Is added scope putting the date or quality bar at risk?
- Do added items need executive approval or deferral?

#### Metric: Scope removed 7d

Counts tickets removed from the release in the recent scope window. It helps separate healthy trade-offs from unstable release planning.

Should answer the following questions:

- Are we protecting the release by deliberately reducing scope?
- Are removals changing stakeholder expectations?
- Do we need to communicate a scope trade-off?

#### Metric: Open high-severity bugs

Counts unresolved high-severity defects in the release. This is a direct quality risk because serious bugs can block approval even when delivery progress looks healthy.

Missing issue type, severity, or status can make the count a Partial confirmed minimum. Empty scope is Not computed and does not present zero as healthy evidence.

Should answer the following questions:

- Is quality acceptable for release approval?
- Which critical defects still need management attention?
- Should the team prioritize quality over new scope?

#### Metric: Reopen events per 100 eligible tickets

Counts every transition from done back to a non-done status per 100 eligible tickets. An eligible ticket is currently done or has recorded evidence that it reached done. The same ticket is counted once for every distinct reopen event, so the value can exceed 100. Reopen-event evidence names any ticket counted more than once. A high value signals acceptance churn, missed requirements, or quality gaps.

If relevant current status or Jira history is incomplete, confirmed event and eligible-ticket counts remain evidence but the percentage is withheld as Partial.

Should answer the following questions:

- Is completed work staying done?
- Are acceptance or quality standards creating rework?
- Do we need tighter validation before release approval?

#### Metric: Median cycle time

Shows the median duration from each eligible ticket's earliest transition into a configured in-progress status to its first later transition into a configured done status. Only the first valid pair per ticket is used.

If a potentially eligible ticket has missing status or incomplete history, the median is withheld as Partial. Complete evidence with no valid transition pair is Not computed.

Should answer the following questions:

- Is work flowing fast enough to protect the release date?
- Are tickets spending too long in progress or review?
- Do we need to remove process, dependency, or capacity bottlenecks?

#### Metric: Open blockers

Counts unresolved blocking issues in the release. Blockers are treated as release risk because they can prevent completion, validation, or approval.

Missing status or insufficient blocker-classification evidence can make the count a Partial confirmed minimum. Empty scope is Not computed.

Should answer the following questions:

- What is stopping the release from moving forward?
- Which blockers require escalation or ownership decisions?
- Can the release proceed while these blockers remain open?

#### Metric: Release confidence

Combines release metrics into a single readiness-confidence value. It is useful for leadership scanning, but should always be read with the risk drivers behind it.

When Jira classification inputs are incomplete, the score is withheld. A confirmed hard-red risk still remains RED; otherwise the release is shown as Inconclusive until the missing Jira fields are completed and metrics are recomputed.

Should answer the following questions:

- What is the current confidence level for this release?
- Is the release improving, stable, or deteriorating?
- Which underlying metrics explain the score?

#### Derived view: Readiness and gates

Shows how much of the release-readiness logic is passing. Gates make the readiness decision explainable instead of relying on a subjective status.

Should answer the following questions:

- Which release conditions are passing or failing?
- Are there hard gates blocking readiness?
- Can leadership explain a go/no-go decision with the stored evidence?

## Sprints

The Sprints area explains whether the active sprint supports the release plan. Sprint Intelligence focuses on current delivery health, while Reports & Evidence preserves trends, reliability, and ticket-level context.

### Sprint Intelligence: Executive Reporting

Sprint Executive Reporting creates a structured snapshot of sprint health for delivery reviews and leadership updates.

Should answer the following questions:

- Can we explain the sprint state without manually reading every Jira ticket?
- What does the current sprint evidence say about release support?
- Do we have evidence ready for delivery conversations?

### Sprint Intelligence: Delivery Confidence

Delivery Confidence combines progress alignment, velocity fit, blocker health, and scope stability into one deterministic sprint health score. Meeting the story-point threshold is necessary but not sufficient: every pointed ticket needs a status, blocker classification must be complete, sprint duration must be valid, and project sprint-membership history must be complete.

If any required non-point input is missing, the score, component breakdown, and biggest driver are withheld. Delivery confidence is shown as Inconclusive with explanations and sorted affected Jira keys, while independently computable ticket metrics remain available.

Should answer the following questions:

- Does the current sprint evidence support its current delivery plan?
- Which component is pulling delivery confidence down?
- Are any required confidence inputs incomplete?

### Sprint Intelligence: Recommended Actions

Sprint Recommended Actions prioritize rule-based responses by configured confidence impact, effort, and category. Confidence impact is an ordering aid, not a forecast of the score after the action.

Should answer the following questions:

- What should the team focus on next to improve sprint confidence?
- Which active rule carries the largest configured confidence impact?
- Are we responding to delivery, quality, flow, or risk issues?

### Sprint Intelligence: Metrics

Sprint Metrics organize delivery, quality, flow, risk, and work-state indicators into scan-friendly cards.

Should answer the following questions:

- How much current sprint scope is done, active, or not started?
- Are high-severity bugs or reopened tickets creating quality risk?
- Is cycle time or blocker health slowing delivery?
- Is work concentrated in a way that creates delivery exposure?

### Sprint Reports: Charts

Sprint Charts show delivery confidence trends, confidence breakdown history, commitment reliability, scope change, quality trend, flow trend, risk heatmap, and sprint evolution.

Should answer the following questions:

- Is sprint confidence trending up or down?
- What does recent stored commitment and completion evidence show?
- Is scope movement destabilizing delivery?
- Which risk areas are repeatedly active across snapshots?

### Sprint Reports: Sprint Health Stats

Sprint Health Stats expose sprint metadata, snapshot timing, and recompute controls so the team can validate the data being reviewed.

Should answer the following questions:

- Which sprint and date range are we reviewing?
- Is the sprint snapshot current?
- Do we need to recompute after Jira updates?

### Sprint Reports: Ticket Situation

Ticket Situation lists sprint issues and their status so leaders can connect sprint metrics to the actual work behind them.

Should answer the following questions:

- Which sprint tickets are still open or blocked?
- Which tickets explain the current delivery confidence?
- Can the team trace sprint risk back to concrete Jira work?

### Sprint metric definitions

These metrics explain whether the current sprint evidence supports the release plan. They connect current scope, progress, quality, flow, blockers, scope stability, and delivery confidence to concrete sprint decisions.

#### Metric: Current sprint scope

Counts distinct tickets currently linked to the sprint at snapshot time. The API retains the field name `committed_scope` for compatibility, but this metric describes current membership and does not reconstruct the sprint-start commitment. An empty current scope is shown as unavailable rather than zero.

Should answer the following questions:

- How many tickets are currently in the sprint?
- Which tickets define the scope measured by the current snapshot?
- Is the current Jira sprint membership complete and up to date?

#### Metric: Completed scope

Shows the percentage of current sprint tickets whose current status is configured as done. It is ticket-based and does not use story points. Empty scope is unavailable, and missing ticket statuses make the percentage partial with the affected Jira keys identified.

Should answer the following questions:

- Is the sprint progressing fast enough?
- How much of the current ticket scope is already finished?
- Do we need to narrow focus to complete remaining work?

#### Derived view: Sprint scope movement

Summarizes confirmed sprint additions and removals after the sprint starts. It is a derived presentation of stored scope-stability evidence, not a forecast of whether the sprint will finish.

Should answer the following questions:

- Is sprint scope stable after planning?
- Are new requests interrupting the sprint commitment?
- Should added work move to the next planning cycle?

#### Derived view: Velocity health

Compares current completed work with the eligible historical velocity baseline used by delivery confidence. It describes the current calculation inputs and does not predict future output.

Should answer the following questions:

- Is the team delivering at a healthy pace?
- Is current output below recent sprint history?
- Do capacity or priority decisions need attention?

#### Derived view: Historical commitment reliability

Shows how recent closed sprints compare committed and completed work when the required stored evidence is available. It describes historical consistency and is not a probability for the current sprint.

Should answer the following questions:

- How did recent closed sprints compare committed and completed work?
- Is the stored historical pattern becoming more or less consistent?
- Should planning assumptions be adjusted?

#### Metric: Open high-severity bugs

Counts unresolved serious defects inside the sprint. It shows whether sprint delivery is carrying quality risk that could affect the release.

Missing issue type, severity, or status can make this a Partial confirmed minimum. Empty current sprint scope is Not computed.

Should answer the following questions:

- Is the sprint producing or carrying critical quality risk?
- Should defect resolution take priority over feature work?
- Are sprint quality issues reducing current release readiness?

#### Metric: Bugs created during sprint

Counts current-sprint bugs whose Jira creation time falls inside the inclusive sprint window. Missing sprint start makes the metric unavailable, while missing Jira creation time makes the count Partial and exposes the affected Jira keys. Local database insertion time is never substituted.

Should answer the following questions:

- Is new defect work consuming sprint capacity?
- Are quality issues emerging during execution?
- Do we need to protect time for stabilization?

#### Metric: Reopen events per 100 eligible tickets

Counts every transition from done back to a non-done status per 100 eligible sprint tickets. An eligible ticket is currently done or has recorded evidence that it reached done. The same ticket is counted once for every distinct reopen event, so the value can exceed 100. Reopen-event evidence names any ticket counted more than once. A high value signals rework, acceptance churn, or incomplete validation.

Incomplete status or history evidence withholds the percentage as Partial while retaining confirmed event evidence.

Should answer the following questions:

- Is sprint work really complete when marked done?
- Are acceptance criteria or quality checks clear enough?
- Is rework putting the sprint goal at risk?

#### Metric: Median cycle time

Shows the median first valid in-progress-to-done duration for eligible current-sprint tickets. Missing status or incomplete history withholds the median as Partial; complete evidence with no valid pair is Not computed.

Should answer the following questions:

- Is sprint work moving through the system fast enough?
- Where might work be stuck?
- Do we need to address review, dependency, or handoff bottlenecks?

#### Metric: Open blockers

Counts unresolved blockers in the sprint. Blockers directly threaten sprint completion and often need escalation before normal delivery can continue.

Missing status or incomplete blocker classification can make this a Partial confirmed minimum. Empty current sprint scope is Not computed.

Should answer the following questions:

- What is preventing sprint work from progressing?
- Which blockers need ownership or escalation?
- Do the open blockers put the current sprint goal at risk?

#### Metric: Unfinished closed-sprint scope

Counts tickets that remain in the current membership of a closed sprint and have a known non-done status. This does not prove that a ticket entered another sprint. The metric is not applicable to active, future, or unknown-state sprints.

Should answer the following questions:

- How many currently assigned tickets are unfinished after the sprint closed?
- Which known unfinished tickets need follow-up?
- Are any ticket statuses missing, making the count partial?

#### Metric: Workload concentration

Shows the top assignee's share of included active sprint story points using the backend's configured done-status rules. Below the required sprint story-point coverage the result is Inconclusive; partial coverage excludes unpointed active tickets and identifies them. A missing stable assignee identity can also make the result Partial while retaining deterministic grouping evidence. No active work is Not applicable, and a zero-point denominator is Not computed. The catalog-defined healthy, watch, and critical bands are applied to the authoritative stored result, which is reused by recommendations, reports, and the dashboard.

Should answer the following questions:

- Is too much critical work dependent on one person?
- Should work be rebalanced to reduce delivery risk?
- Is capacity hidden behind a single overloaded owner?
- Is the result partial or inconclusive because required Jira evidence is missing?

#### Derived view: Sprint work state

Condenses current sprint scope, in-progress, not-started, done, and applicable unfinished closed-sprint work into one scan-friendly view of sprint execution.

Should answer the following questions:

- How is sprint work distributed across states?
- Is too much work not started or still active late in the sprint?
- Does the sprint state support the delivery-confidence score?

#### Metric: Delivery confidence

Combines progress alignment, velocity fit, blocker health, and scope stability into a single sprint confidence score. An empty sprint is Not computed, and coverage below half of current sprint tickets is Inconclusive with no score. From the minimum coverage to below complete coverage, the score is Partial and point-based components use only pointed tickets. At complete story-point coverage, the score is Computed only when the required status, blocker-classification, duration, and project sprint-history evidence is also complete; otherwise it remains Inconclusive.

Should answer the following questions:

- Does the current sprint evidence support its commitment?
- Which confidence component is pulling the sprint down?
- Is the result Inconclusive because required evidence is missing?

#### Delivery-confidence component: Progress alignment

Compares completed scope with elapsed sprint time. It requires valid sprint start and end times; missing or invalid duration makes the component unavailable rather than healthy.

Should answer the following questions:

- Is progress keeping pace with time elapsed?
- Is the sprint behind even if some work is complete?
- Should the team focus on finishing rather than starting?

#### Delivery-confidence component: Velocity fit

Checks whether remaining sprint work fits the team's historical delivery capacity. It uses valid sprint duration to calculate remaining time and never substitutes a healthy time or capacity fallback when duration is unavailable.

Should answer the following questions:

- Does the remaining work fit the team's documented historical capacity?
- Is the sprint plan larger than recent delivery capacity?
- Do we need a scope or staffing decision?

#### Delivery-confidence component: Scope stability

Scores how stable sprint scope has been since the initial commitment. It requires a sprint start and complete sprint-membership history across synchronized project tickets; otherwise the component and delivery confidence are unavailable.

Should answer the following questions:

- Is the team executing a stable plan?
- Are scope changes weakening confidence?
- Should leadership protect the sprint from late additions?
