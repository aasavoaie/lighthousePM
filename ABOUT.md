# Lighthouse PM

## Overview

### What the product does

LighthousePM turns Jira release and sprint activity into deterministic delivery metrics, release readiness signals, and recommended actions. It is built for teams that need a clear view of blockers, quality risk, scope movement, flow health, and confidence trends before release decisions are made.

The product is organized around:

- Release Intelligence: confidence, readiness, critical risks, warnings, tickets, and release-level trend history.
- Sprint Intelligence: progress alignment, active work, blockers, sprint-created bugs, rollover, and predictability.
- Explainable Signals: every confidence signal is tied to explicit metrics, thresholds, reasons, and risk contribution.
- Operational Evidence: reports preserve the charts, aging detail, comparison data, and ticket context behind each decision.

### What the Overview shows

The Overview section is the executive decision view of LighthousePM. It gives a Head of PO, CEO, or Head of PM a single place to understand whether the selected release is still a responsible business commitment, what is creating delivery or quality risk, and which actions should be taken first to protect the release outcome.

Instead of asking leadership to inspect Jira issue by issue, the screen turns release and sprint activity into deterministic evidence. It supports release governance with clear signals: current confidence, trend direction, active risks, the current Release Outlook, recommended actions, and current sprint context.

#### Release Readiness

Release Readiness is the executive release health indicator. It shows whether the release is currently tracking as ready, needs management attention, or should be treated as a serious release risk.

Should answer the following questions:

- Can we still stand behind this release commitment?
- Is the release healthy enough to continue without intervention?
- What message should leadership use with stakeholders?
- Do we need a go/no-go discussion, scope decision, or escalation?

The score and label are based on computed release data, not manual judgment.

#### Confidence Engine

The Confidence Engine explains what is reducing confidence in the release. It identifies the strongest negative drivers, such as high-severity bugs, scope churn, reopen rate, blockers, or cycle time.

Should answer the following questions:

- What is the biggest reason confidence is dropping?
- Is the problem delivery, quality, flow, scope control, or unresolved risk?
- Which leadership lever is needed: prioritization, scope trade-off, escalation, or team focus?
- Where should management attention go first?

This turns a vague release concern into specific, explainable causes that can be discussed with the team and stakeholders.

#### Confidence Trend

The Confidence Trend shows whether release confidence is improving, stable, or deteriorating over time. It gives leadership a view of momentum, not only the current status.

Should answer the following questions:

- Are we getting closer to a safe release or further away from it?
- Did recent delivery decisions improve the release outlook?
- Is the trend strong enough to support the planned release date?
- Do we need to change the plan before the risk becomes harder to recover?

The trend also shows the change since the first snapshot, making it easier to explain movement in leadership updates.

#### Release Outlook

Release Outlook summarizes the latest stored release evidence. It shows the current confidence and final signal, passed and failed release gates, confidence change against the latest available 24-hour baseline, calendar days remaining until the Jira release date, and active hard RED and YELLOW conditions.

Should answer the following questions:

- What does the current release signal say about the release commitment?
- Which release gates are currently passing or failing?
- Has confidence improved or deteriorated against the available 24-hour baseline?
- How many calendar days remain, and which active conditions require attention now?

Release Outlook is not a forecast. It does not estimate a probability, predict future confidence, or claim a chance of meeting the release target. It helps leadership act on the evidence that is currently available.

#### Risk Aging

Risk Aging shows how long major release risks have been open, focused especially on blockers and high-severity bugs.

Should answer the following questions:

- Are serious risks staying open long enough to threaten the release?
- Are old unresolved issues reducing confidence in the delivery plan?
- Which risks need leadership attention because they are not moving?
- Is there still enough time to fix and verify critical work before release?

Aging risks matter because unresolved critical work compresses the time available for validation and increases current delivery risk.

#### Recommended Actions

Recommended Actions lists the next best actions to improve release confidence. Each action includes a priority, category, effort level, and expected confidence gain.

Should answer the following questions:

- What should the organization do next to improve the release outcome?
- Which action gives the highest expected confidence gain?
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
- Are quality indicators such as high-severity bugs and reopen rate acceptable?
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

Should answer the following questions:

- Is enough release scope complete for the planned date?
- Is delivery progress aligned with the business expectation?
- Do we need to reduce scope or increase delivery focus?

#### Metric: Completed tickets

Counts the release tickets already finished. It gives leadership a concrete volume of delivered work behind the completion percentage.

Should answer the following questions:

- How much work has actually landed?
- Is progress supported by completed Jira items?
- Can we explain release progress with ticket-level evidence?

#### Metric: Scope creep

Measures recent release scope movement over the last seven days. High churn means the release target is still changing while the team is trying to finish it.

Should answer the following questions:

- Is the release commitment stable enough to govern?
- Are new requests or removals changing the delivery promise late?
- Should leadership freeze scope or defer non-critical work?

#### Metric: Scope added

Counts tickets added to the release in the recent scope window. It explains whether churn is caused by new work entering the release.

Should answer the following questions:

- What new work has entered the release recently?
- Is added scope putting the date or quality bar at risk?
- Do added items need executive approval or deferral?

#### Metric: Scope removed

Counts tickets removed from the release in the recent scope window. It helps separate healthy trade-offs from unstable release planning.

Should answer the following questions:

- Are we protecting the release by deliberately reducing scope?
- Are removals changing stakeholder expectations?
- Do we need to communicate a scope trade-off?

#### Metric: Open high-severity bugs

Counts unresolved high-severity defects in the release. This is a direct quality risk because serious bugs can block approval even when delivery progress looks healthy.

Should answer the following questions:

- Is quality acceptable for release approval?
- Which critical defects still need management attention?
- Should the team prioritize quality over new scope?

#### Metric: Reopen rate

Shows the percentage of work reopened after it was considered done. A high reopen rate signals acceptance churn, missed requirements, or quality gaps.

Should answer the following questions:

- Is completed work staying done?
- Are acceptance or quality standards creating rework?
- Do we need tighter validation before release approval?

#### Metric: Median cycle time

Shows the typical time work spends from active start to done. Longer cycle time means work is moving slowly through the delivery system.

Should answer the following questions:

- Is work flowing fast enough to protect the release date?
- Are tickets spending too long in progress or review?
- Do we need to remove process, dependency, or capacity bottlenecks?

#### Metric: Open blockers

Counts unresolved blocking issues in the release. Blockers are treated as release risk because they can prevent completion, validation, or approval.

Should answer the following questions:

- What is stopping the release from moving forward?
- Which blockers require escalation or ownership decisions?
- Can the release proceed while these blockers remain open?

#### Metric: Confidence score

Combines release metrics into a single readiness-confidence value. It is useful for leadership scanning, but should always be read with the risk drivers behind it.

Should answer the following questions:

- What is the current confidence level for this release?
- Is the release improving, stable, or deteriorating?
- Which underlying metrics explain the score?

#### Metric: Readiness percent and gates

Shows how much of the release-readiness logic is passing. Gates make the readiness decision explainable instead of relying on a subjective status.

Should answer the following questions:

- Which release conditions are passing or failing?
- Are there hard gates blocking readiness?
- Can leadership defend the go/no-go recommendation with evidence?

## Sprints

The Sprints area explains whether the active sprint supports the release plan. Sprint Intelligence focuses on current delivery health, while Reports & Evidence preserves trends, reliability, and ticket-level context.

### Sprint Intelligence: Executive Reporting

Sprint Executive Reporting creates a structured snapshot of sprint health for delivery reviews and leadership updates.

Should answer the following questions:

- Can we explain the sprint state without manually reading every Jira ticket?
- Is the sprint on track to support release expectations?
- Do we have evidence ready for delivery conversations?

### Sprint Intelligence: Delivery Confidence

Delivery Confidence combines progress alignment, velocity fit, blocker health, and scope stability into one deterministic sprint health score.

Should answer the following questions:

- Does the current sprint evidence support the committed work?
- Which component is pulling delivery confidence down?
- Is the problem progress, velocity, blockers, or scope instability?

### Sprint Intelligence: Recommended Actions

Sprint Recommended Actions prioritize the next team moves by expected confidence gain, effort, and category.

Should answer the following questions:

- What should the team focus on next to improve sprint confidence?
- Which action has the highest expected delivery impact?
- Are we responding to delivery, quality, flow, or risk issues?

### Sprint Intelligence: Metrics

Sprint Metrics organize delivery, quality, flow, risk, and work-state indicators into scan-friendly cards.

Should answer the following questions:

- How much committed scope is done, active, or not started?
- Are high-severity bugs or reopened tickets creating quality risk?
- Is cycle time or blocker health slowing delivery?
- Is work concentrated in a way that creates delivery exposure?

### Sprint Reports: Charts

Sprint Charts show delivery confidence trends, confidence breakdown history, commitment reliability, scope change, quality trend, flow trend, risk heatmap, and sprint evolution.

Should answer the following questions:

- Is sprint confidence trending up or down?
- Are recent sprints predictable against commitments?
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

These metrics explain whether the current sprint evidence supports the release plan. They connect commitment, progress, quality, flow, blockers, scope stability, and delivery confidence to concrete sprint decisions.

#### Metric: Committed scope

Counts issues explicitly linked to the sprint. It defines the sprint promise that progress, confidence, and predictability are measured against.

Should answer the following questions:

- What did the team commit to deliver?
- Is the sprint scope clear enough to manage?
- Are we measuring progress against the right work?

#### Metric: Completed scope

Shows the percentage of committed sprint scope already done. It is the core indicator of whether the sprint is converting commitment into finished work.

Should answer the following questions:

- Is the sprint progressing fast enough?
- How much committed work is already finished?
- Do we need to narrow focus to complete remaining work?

#### Metric: Scope creep

Shows scope movement after the sprint starts. High creep means the sprint plan is changing while the team is executing, which reduces predictability.

Should answer the following questions:

- Is sprint scope stable after planning?
- Are new requests interrupting the sprint commitment?
- Should added work move to the next planning cycle?

#### Metric: Velocity health

Compares current completed work to historical sprint velocity. It indicates whether the sprint is tracking close to the team's normal delivery capacity.

Should answer the following questions:

- Is the team delivering at a healthy pace?
- Is current output below recent sprint history?
- Do capacity or priority decisions need attention?

#### Metric: Team predictability

Shows how reliably recent closed sprints completed committed work. It helps leadership understand whether the team has a stable delivery pattern.

Should answer the following questions:

- Can we trust sprint commitments based on recent history?
- Is the team becoming more or less predictable?
- Should planning assumptions be adjusted?

#### Metric: Open high-severity bugs

Counts unresolved serious defects inside the sprint. It shows whether sprint delivery is carrying quality risk that could affect the release.

Should answer the following questions:

- Is the sprint producing or carrying critical quality risk?
- Should defect resolution take priority over feature work?
- Are sprint quality issues reducing current release readiness?

#### Metric: Bugs created during sprint

Counts bugs opened during the sprint. This helps leadership see when planned delivery is being displaced by newly discovered quality work.

Should answer the following questions:

- Is new defect work consuming sprint capacity?
- Are quality issues emerging during execution?
- Do we need to protect time for stabilization?

#### Metric: Reopen rate

Shows how often sprint work is reopened after being treated as done. Reopened work is a signal of rework, acceptance churn, or incomplete validation.

Should answer the following questions:

- Is sprint work really complete when marked done?
- Are acceptance criteria or quality checks clear enough?
- Is rework putting the sprint goal at risk?

#### Metric: Median cycle time

Shows the typical time sprint work takes from active start to done. It helps reveal whether work is flowing smoothly through implementation, review, and validation.

Should answer the following questions:

- Is sprint work moving through the system fast enough?
- Where might work be stuck?
- Do we need to address review, dependency, or handoff bottlenecks?

#### Metric: Open blockers

Counts unresolved blockers in the sprint. Blockers directly threaten sprint completion and often need escalation before normal delivery can continue.

Should answer the following questions:

- What is preventing sprint work from progressing?
- Which blockers need ownership or escalation?
- Do the open blockers put the current sprint goal at risk?

#### Metric: Rollover

Counts work that did not finish by sprint close. Rollover indicates planning, capacity, dependency, or execution issues that can reduce predictability.

Should answer the following questions:

- How much work is carrying into the next sprint?
- Is rollover becoming a repeat delivery pattern?
- Do planning assumptions need to change?

#### Metric: Work distribution

Shows whether active sprint work is concentrated with one assignee. Heavy concentration creates delivery exposure even when total progress looks acceptable.

Should answer the following questions:

- Is too much critical work dependent on one person?
- Should work be rebalanced to reduce delivery risk?
- Is capacity hidden behind a single overloaded owner?

#### Metric: Sprint work state

Condenses committed, active, not-started, done, and rollover work into one scan-friendly view of sprint execution.

Should answer the following questions:

- How is sprint work distributed across states?
- Is too much work not started or still active late in the sprint?
- Does the sprint state support the delivery-confidence score?

#### Metric: Delivery confidence score

Combines progress alignment, velocity fit, blocker health, and scope stability into a single sprint confidence score.

Should answer the following questions:

- Does the current sprint evidence support its commitment?
- Which confidence component is pulling the sprint down?
- Should leadership intervene on progress, capacity, blockers, or scope?

#### Metric: Progress alignment

Compares completed scope with elapsed sprint time. It shows whether the team is far enough through the work for where it is in the sprint.

Should answer the following questions:

- Is progress keeping pace with time elapsed?
- Is the sprint behind even if some work is complete?
- Should the team focus on finishing rather than starting?

#### Metric: Velocity fit

Checks whether remaining sprint work fits the team's historical delivery capacity. It turns velocity history into a current capacity-fit signal.

Should answer the following questions:

- Does the remaining work fit the team's documented historical capacity?
- Is the sprint plan larger than recent delivery capacity?
- Do we need a scope or staffing decision?

#### Metric: Scope stability

Scores how stable sprint scope has been since the initial commitment. Lower stability means the sprint is changing after planning.

Should answer the following questions:

- Is the team executing a stable plan?
- Are scope changes weakening confidence?
- Should leadership protect the sprint from late additions?
