import { useState } from "react";

import { apiClient } from "../api/client";
import { savePdfBlob } from "../components/ReportExportActions";

type AboutGuidePage = "overview" | "releases" | "sprints";

type AboutGuideSection = {
  title: string;
  description: string;
  questions: string[];
  note?: string;
};

const aboutOverviewSections: AboutGuideSection[] = [
  {
    title: "Release Readiness",
    description:
      "Release Readiness is the executive release health indicator. It shows whether the release is currently tracking as ready, needs management attention, or should be treated as a serious release risk.",
    questions: [
      "Can we still stand behind this release commitment?",
      "Is the release healthy enough to continue without intervention?",
      "What message should leadership use with stakeholders?",
      "Do we need a go/no-go discussion, scope decision, or escalation?",
    ],
    note: "The score and label are based on computed release data, not manual judgment.",
  },
  {
    title: "Confidence Engine",
    description:
      "The Confidence Engine explains what is reducing confidence in the release and identifies the strongest negative drivers.",
    questions: [
      "What is the biggest reason confidence is dropping?",
      "Is the problem delivery, quality, flow, scope control, or unresolved risk?",
      "Which leadership lever is needed: prioritization, scope trade-off, escalation, or team focus?",
      "Where should management attention go first?",
    ],
  },
  {
    title: "Confidence Trend",
    description:
      "Confidence Trend shows whether release confidence is improving, stable, or deteriorating over time.",
    questions: [
      "Are we getting closer to a safe release or further away from it?",
      "Did recent delivery decisions improve the release outlook?",
      "Is the trend strong enough to support the planned release date?",
      "Do we need to change the plan before the risk becomes harder to recover?",
    ],
  },
  {
    title: "Release Outlook",
    description:
      "Release Outlook summarizes current confidence, release gates, 24-hour change, time to the Jira release date, and active conditions. It is not a forecast.",
    questions: [
      "What does the latest stored snapshot say about release readiness?",
      "Which release gates currently pass or fail?",
      "Should we reduce scope, increase focus on quality, move the date, or escalate?",
      "Which active RED or YELLOW conditions need attention?",
    ],
  },
  {
    title: "Risk Aging",
    description:
      "Risk Aging shows how long major release risks have been open, focused especially on blockers and high-severity bugs.",
    questions: [
      "Are serious risks staying open long enough to threaten the release?",
      "Are old unresolved issues reducing confidence in the delivery plan?",
      "Which risks need leadership attention because they are not moving?",
      "Is there still enough time to fix and verify critical work before release?",
    ],
  },
  {
    title: "Recommended Actions",
    description:
      "Recommended Actions lists the next best actions to improve release confidence with priority, effort, category, and expected gain.",
    questions: [
      "What should the organization do next to improve the release outcome?",
      "Which action gives the highest expected confidence gain?",
      "Are we solving the right category of problem: delivery, quality, flow, or risk?",
      "What should leadership ask the team to focus on now?",
    ],
  },
  {
    title: "Additional Warnings",
    description:
      "Additional Warnings lists active risk messages that are not always the largest confidence drivers but still need visibility.",
    questions: [
      "What secondary risks should leadership keep visible?",
      "Are any warning signs likely to become executive issues later?",
      "What should be included in release governance or stakeholder updates?",
      "Which risks should be monitored even if they are not the top blocker today?",
    ],
  },
  {
    title: "Active Sprint",
    description:
      "Active Sprint connects release health to the sprint currently in progress and shows sprint delivery confidence when available.",
    questions: [
      "Is the current sprint supporting the release plan or putting it under pressure?",
      "Does sprint delivery confidence match the release expectation?",
      "Is the team likely to close the work needed for the release?",
      "Do sprint risks require scope, priority, or capacity decisions?",
    ],
  },
];

const aboutReleaseSections: AboutGuideSection[] = [
  {
    title: "Command Center: Executive Reporting",
    description:
      "Executive Reporting creates a consistent release export for governance, stakeholder communication, and release reviews.",
    questions: [
      "Can we produce a clear release summary for leadership?",
      "Is the current release state easy to share outside the delivery team?",
      "Do we have evidence ready for a go/no-go or steering conversation?",
    ],
  },
  {
    title: "Command Center: Release Confidence Signal",
    description:
      "Release Confidence Signal summarizes readiness, confidence, release gates, critical risks, warnings, risk aging, confidence breakdown, and the biggest confidence drag.",
    questions: [
      "Is this release green, yellow, or red for explainable reasons?",
      "Which gates are blocking readiness?",
      "What is the single largest risk driver leadership should discuss?",
      "Are blockers, high-severity bugs, or warnings aging too long?",
    ],
  },
  {
    title: "Command Center: Metrics",
    description:
      "Metrics groups release health into Delivery, Quality, Flow, and Risk so leaders can see the measurable causes behind readiness.",
    questions: [
      "Is scope being completed fast enough?",
      "Is scope churn changing the release commitment?",
      "Are quality indicators such as high-severity bugs and reopen events per 100 eligible tickets acceptable?",
      "Are flow or blocker risks delaying release confidence?",
    ],
  },
  {
    title: "Command Center: Release Controls and Tickets",
    description:
      "Release controls and tickets connect the selected release, recomputed snapshots, and issue-level evidence behind the current status.",
    questions: [
      "Are we reviewing the right release?",
      "Were metrics recomputed after the latest Jira changes?",
      "Which unresolved tickets explain the release status?",
    ],
  },
  {
    title: "Reports & Evidence: Release Charts",
    description:
      "Release Charts preserve historical proof through confidence evolution, risk breakdown, quality gates, readiness, blocker aging, and release comparison.",
    questions: [
      "Is confidence improving or deteriorating over time?",
      "Which risks contribute most to the current confidence score?",
      "Are quality gates and readiness moving in the right direction?",
      "How does this release compare with other recent releases?",
    ],
  },
  {
    title: "Reports & Evidence: Tickets",
    description:
      "Tickets provide issue-level evidence behind release metrics and reports, with filters for not-done and completed work.",
    questions: [
      "Which unresolved tickets still affect the release decision?",
      "Which completed tickets support release progress?",
      "Can leadership trace every signal back to concrete Jira work?",
    ],
  },
];

const aboutReleaseMetricSections: AboutGuideSection[] = [
  {
    title: "Metric: Scope completed",
    description:
      "Shows the percentage of release scope that is done. This is the simplest delivery-progress signal for the release commitment.",
    questions: [
      "Is enough release scope complete for the planned date?",
      "Is delivery progress aligned with the business expectation?",
      "Do we need to reduce scope or increase delivery focus?",
    ],
  },
  {
    title: "Metric: Completed tickets",
    description:
      "Counts the release tickets already finished. It gives leadership a concrete volume of delivered work behind the completion percentage.",
    questions: [
      "How much work has actually landed?",
      "Is progress supported by completed Jira items?",
      "Can we explain release progress with ticket-level evidence?",
    ],
  },
  {
    title: "Metric: Scope creep",
    description:
      "Measures recent release scope movement over the last seven days. High churn means the release target is still changing while the team is trying to finish it.",
    questions: [
      "Is the release commitment stable enough to govern?",
      "Are new requests or removals changing the delivery promise late?",
      "Should leadership freeze scope or defer non-critical work?",
    ],
  },
  {
    title: "Metric: Scope added",
    description:
      "Counts tickets added to the release in the recent scope window. It explains whether churn is caused by new work entering the release.",
    questions: [
      "What new work has entered the release recently?",
      "Is added scope putting the date or quality bar at risk?",
      "Do added items need executive approval or deferral?",
    ],
  },
  {
    title: "Metric: Scope removed",
    description:
      "Counts tickets removed from the release in the recent scope window. It helps separate healthy trade-offs from unstable release planning.",
    questions: [
      "Are we protecting the release by deliberately reducing scope?",
      "Are removals changing stakeholder expectations?",
      "Do we need to communicate a scope trade-off?",
    ],
  },
  {
    title: "Metric: Open high-severity bugs",
    description:
      "Counts unresolved high-severity defects in the release. This is a direct quality risk because serious bugs can block approval even when delivery progress looks healthy.",
    questions: [
      "Is quality acceptable for release approval?",
      "Which critical defects still need management attention?",
      "Should the team prioritize quality over new scope?",
    ],
  },
  {
    title: "Metric: Reopen events per 100 eligible tickets",
    description:
      "Counts every transition from done back to a non-done status per 100 eligible tickets. An eligible ticket is currently done or has recorded evidence that it reached done. The same ticket is counted once for every distinct reopen event, so the value can exceed 100. Reopen-event evidence names any ticket counted more than once. A high value signals acceptance churn, missed requirements, or quality gaps.",
    questions: [
      "Is completed work staying done?",
      "Are acceptance or quality standards creating rework?",
      "Do we need tighter validation before release approval?",
    ],
  },
  {
    title: "Metric: Median cycle time",
    description:
      "Shows the typical time work spends from active start to done. Longer cycle time means work is moving slowly through the delivery system.",
    questions: [
      "Is work flowing fast enough to protect the release date?",
      "Are tickets spending too long in progress or review?",
      "Do we need to remove process, dependency, or capacity bottlenecks?",
    ],
  },
  {
    title: "Metric: Open blockers",
    description:
      "Counts unresolved blocking issues in the release. Blockers are treated as release risk because they can prevent completion, validation, or approval.",
    questions: [
      "What is stopping the release from moving forward?",
      "Which blockers require escalation or ownership decisions?",
      "Can the release proceed while these blockers remain open?",
    ],
  },
  {
    title: "Metric: Confidence score",
    description:
      "Combines release metrics into a single readiness-confidence value. It is useful for leadership scanning, but should always be read with the risk drivers behind it.",
    questions: [
      "What is the current confidence level for this release?",
      "Is the release improving, stable, or deteriorating?",
      "Which underlying metrics explain the score?",
    ],
  },
  {
    title: "Metric: Readiness percent and gates",
    description:
      "Shows how much of the release-readiness logic is passing. Gates make the readiness decision explainable instead of relying on a subjective status.",
    questions: [
      "Which release conditions are passing or failing?",
      "Are there hard gates blocking readiness?",
      "Can leadership defend the go/no-go recommendation with evidence?",
    ],
  },
];

const aboutSprintSections: AboutGuideSection[] = [
  {
    title: "Sprint Intelligence: Executive Reporting",
    description:
      "Sprint Executive Reporting creates a structured snapshot of sprint health for delivery reviews and leadership updates.",
    questions: [
      "Can we explain the sprint state without manually reading every Jira ticket?",
      "Is the sprint on track to support release expectations?",
      "Do we have evidence ready for delivery conversations?",
    ],
  },
  {
    title: "Sprint Intelligence: Delivery Confidence",
    description:
      "Delivery Confidence combines progress alignment, velocity fit, blocker health, and scope stability into one deterministic sprint health score. Story-point coverage is necessary but the required status, blocker-classification, duration, and project sprint-history evidence must also be complete.",
    questions: [
      "Does the current sprint evidence support its current delivery plan?",
      "Which component is pulling delivery confidence down?",
      "Are any required confidence inputs incomplete?",
    ],
    note:
      "When required non-point evidence is missing, delivery confidence is Inconclusive and the score, component breakdown, and biggest driver are withheld. Explanations identify the missing input and affected Jira keys while independent ticket metrics remain available.",
  },
  {
    title: "Sprint Intelligence: Recommended Actions",
    description:
      "Sprint Recommended Actions prioritize the next team moves by expected confidence gain, effort, and category.",
    questions: [
      "What should the team focus on next to improve sprint confidence?",
      "Which action has the highest expected delivery impact?",
      "Are we responding to delivery, quality, flow, or risk issues?",
    ],
  },
  {
    title: "Sprint Intelligence: Metrics",
    description:
      "Sprint Metrics organize delivery, quality, flow, risk, and work-state indicators into scan-friendly cards.",
    questions: [
      "How much current sprint scope is done, active, or not started?",
      "Are high-severity bugs or reopened tickets creating quality risk?",
      "Is cycle time or blocker health slowing delivery?",
      "Is work concentrated in a way that creates delivery exposure?",
    ],
  },
  {
    title: "Sprint Reports: Charts",
    description:
      "Sprint Charts show delivery confidence trends, confidence breakdown history, commitment reliability, scope change, quality trend, flow trend, risk heatmap, and sprint evolution.",
    questions: [
      "Is sprint confidence trending up or down?",
      "Are recent sprints predictable against commitments?",
      "Is scope movement destabilizing delivery?",
      "Which risk areas are repeatedly active across snapshots?",
    ],
  },
  {
    title: "Sprint Reports: Sprint Health Stats",
    description:
      "Sprint Health Stats expose sprint metadata, snapshot timing, and recompute controls so the team can validate the data being reviewed.",
    questions: [
      "Which sprint and date range are we reviewing?",
      "Is the sprint snapshot current?",
      "Do we need to recompute after Jira updates?",
    ],
  },
  {
    title: "Sprint Reports: Ticket Situation",
    description:
      "Ticket Situation lists sprint issues and their status so leaders can connect sprint metrics to the actual work behind them.",
    questions: [
      "Which sprint tickets are still open or blocked?",
      "Which tickets explain the current delivery confidence?",
      "Can the team trace sprint risk back to concrete Jira work?",
    ],
  },
];

const aboutSprintMetricSections: AboutGuideSection[] = [
  {
    title: "Metric: Current sprint scope",
    description:
      "Counts distinct tickets currently linked to the sprint at snapshot time. The API retains the field name committed_scope for compatibility, but this metric describes current membership and does not reconstruct the sprint-start commitment. An empty current scope is shown as unavailable rather than zero.",
    questions: [
      "How many tickets are currently in the sprint?",
      "Which tickets define the scope measured by the current snapshot?",
      "Is the current Jira sprint membership complete and up to date?",
    ],
  },
  {
    title: "Metric: Completed scope",
    description:
      "Shows the percentage of current sprint tickets whose current status is configured as done. It is ticket-based and does not use story points. Empty scope is unavailable, and missing ticket statuses make the percentage partial with the affected Jira keys identified.",
    questions: [
      "Is the sprint progressing fast enough?",
      "How much of the current ticket scope is already finished?",
      "Do we need to narrow focus to complete remaining work?",
    ],
  },
  {
    title: "Metric: Scope creep",
    description:
      "Shows sprint addition and removal events after the sprint starts. Re-adding a previously removed ticket counts as another event. High creep means the sprint plan is changing while the team is executing, which reduces predictability.",
    questions: [
      "Is sprint scope stable after planning?",
      "Are new requests interrupting the sprint commitment?",
      "Should added work move to the next planning cycle?",
    ],
  },
  {
    title: "Metric: Velocity health",
    description:
      "Compares current completed work to historical sprint velocity. It indicates whether the sprint is tracking close to the team's normal delivery capacity.",
    questions: [
      "Is the team delivering at a healthy pace?",
      "Is current output below recent sprint history?",
      "Do capacity or priority decisions need attention?",
    ],
  },
  {
    title: "Metric: Team predictability",
    description:
      "Shows how reliably recent closed sprints completed committed work. It helps leadership understand whether the team has a stable delivery pattern.",
    questions: [
      "Can we trust sprint commitments based on recent history?",
      "Is the team becoming more or less predictable?",
      "Should planning assumptions be adjusted?",
    ],
  },
  {
    title: "Metric: Open high-severity bugs",
    description:
      "Counts unresolved serious defects inside the sprint. It shows whether sprint delivery is carrying quality risk that could affect the release.",
    questions: [
      "Is the sprint producing or carrying critical quality risk?",
      "Should defect resolution take priority over feature work?",
      "Will sprint quality issues threaten release readiness?",
    ],
  },
  {
    title: "Metric: Bugs created during sprint",
    description:
      "Counts bugs opened during the sprint. This helps leadership see when planned delivery is being displaced by newly discovered quality work.",
    questions: [
      "Is new defect work consuming sprint capacity?",
      "Are quality issues emerging during execution?",
      "Do we need to protect time for stabilization?",
    ],
  },
  {
    title: "Metric: Reopen events per 100 eligible tickets",
    description:
      "Counts every transition from done back to a non-done status per 100 eligible sprint tickets. An eligible ticket is currently done or has recorded evidence that it reached done. The same ticket is counted once for every distinct reopen event, so the value can exceed 100. Reopen-event evidence names any ticket counted more than once. A high value signals rework, acceptance churn, or incomplete validation.",
    questions: [
      "Is sprint work really complete when marked done?",
      "Are acceptance criteria or quality checks clear enough?",
      "Is rework putting the sprint goal at risk?",
    ],
  },
  {
    title: "Metric: Median cycle time",
    description:
      "Shows the typical time sprint work takes from active start to done. It helps reveal whether work is flowing smoothly through implementation, review, and validation.",
    questions: [
      "Is sprint work moving through the system fast enough?",
      "Where might work be stuck?",
      "Do we need to address review, dependency, or handoff bottlenecks?",
    ],
  },
  {
    title: "Metric: Open blockers",
    description:
      "Counts unresolved blockers in the sprint. Blockers directly threaten sprint completion and often need escalation before normal delivery can continue.",
    questions: [
      "What is preventing sprint work from progressing?",
      "Which blockers need ownership or escalation?",
      "Can the team still meet the sprint goal with these blockers open?",
    ],
  },
  {
    title: "Metric: Unfinished closed-sprint scope",
    description:
      "Counts tickets that remain in the current membership of a closed sprint and have a known non-done status. This does not prove that a ticket entered another sprint. The metric is not applicable to active, future, or unknown-state sprints.",
    questions: [
      "How many currently assigned tickets are unfinished after the sprint closed?",
      "Which known unfinished tickets need follow-up?",
      "Are any ticket statuses missing, making the count partial?",
    ],
  },
  {
    title: "Metric: Work distribution",
    description:
      "Shows the top assignee's share of active sprint story points using the backend's configured done-status rules. Below 50% sprint story-point coverage the result is inconclusive; partial coverage excludes unpointed active tickets and identifies them. No active work is not applicable, and a zero-point denominator is not computed. Below 35% is healthy, 35% through 50% is watch, and above 50% is critical. Recommendations, reports, and the dashboard reuse the stored result and Jira-key evidence.",
    questions: [
      "Is too much critical work dependent on one person?",
      "Should work be rebalanced to reduce delivery risk?",
      "Is capacity hidden behind a single overloaded owner?",
      "Is the result partial or inconclusive because required Jira evidence is missing?",
    ],
  },
  {
    title: "Metric: Sprint work state",
    description:
      "Condenses current sprint scope, in-progress, not-started, done, and applicable unfinished closed-sprint work into one scan-friendly view of sprint execution.",
    questions: [
      "How is sprint work distributed across states?",
      "Is too much work not started or still active late in the sprint?",
      "Does the sprint state support the delivery-confidence score?",
    ],
  },
  {
    title: "Metric: Delivery confidence score",
    description:
      "Combines progress alignment, velocity fit, blocker health, and scope stability into a single sprint confidence score. The score is returned only when required status, blocker-classification, duration, and project sprint-history evidence is complete.",
    questions: [
      "Does current sprint evidence support its delivery plan?",
      "Which confidence component is pulling the sprint down?",
      "Is the result Inconclusive because required evidence is missing?",
    ],
  },
  {
    title: "Metric: Progress alignment",
    description:
      "Compares completed scope with elapsed sprint time. It requires valid sprint start and end times; missing or invalid duration makes the component unavailable rather than healthy.",
    questions: [
      "Is progress keeping pace with time elapsed?",
      "Is the sprint behind even if some work is complete?",
      "Should the team focus on finishing rather than starting?",
    ],
  },
  {
    title: "Metric: Velocity fit",
    description:
      "Checks whether remaining sprint work fits the team's historical delivery capacity. It uses valid sprint duration and never substitutes a healthy time or capacity fallback when duration is unavailable.",
    questions: [
      "Does the remaining work fit the team's documented historical capacity?",
      "Is the sprint plan larger than recent delivery capacity?",
      "Do we need a scope or staffing decision?",
    ],
  },
  {
    title: "Metric: Scope stability",
    description:
      "Scores how stable sprint scope has been since the initial commitment. It requires a sprint start and complete sprint-membership history across synchronized project tickets; otherwise the component and delivery confidence are unavailable.",
    questions: [
      "Is the team executing a stable plan?",
      "Are scope changes weakening confidence?",
      "Should leadership protect the sprint from late additions?",
    ],
  },
];

function AboutGuideCard({ section }: { section: AboutGuideSection }) {
  return (
    <article className="about-guide-card">
      <h3>{section.title}</h3>
      <p>{section.description}</p>
      <h4>Should answer the following questions:</h4>
      <ul>
        {section.questions.map((question) => (
          <li key={question}>{question}</li>
        ))}
      </ul>
      {section.note ? <p>{section.note}</p> : null}
    </article>
  );
}

function AboutGuideGrid({ sections }: { sections: AboutGuideSection[] }) {
  return (
    <div className="about-guide-grid" aria-label="About guide sections">
      {sections.map((section) => (
        <AboutGuideCard key={section.title} section={section} />
      ))}
    </div>
  );
}

function AboutDocumentationExport() {
  const [isExporting, setIsExporting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [status, setStatus] = useState<string | null>(null);

  async function handleExport() {
    if (isExporting) {
      return;
    }
    setIsExporting(true);
    setError(null);
    setStatus(null);
    try {
      const blob = await apiClient.downloadDocumentationReport();
      setStatus(await savePdfBlob(blob, "lighthousepm-documentation.pdf"));
    } catch (exportError) {
      setError(exportError instanceof Error ? exportError.message : "Failed to export documentation PDF.");
    } finally {
      setIsExporting(false);
    }
  }

  return (
    <div className="about-documentation-export" aria-label="Documentation PDF export">
      <button
        type="button"
        className="primary-button compact-button about-export-button"
        disabled={isExporting}
        onClick={() => void handleExport()}
      >
        <span className="about-export-icon" aria-hidden="true" />
        {isExporting ? "Exporting..." : "Export Documentation PDF"}
      </button>
      {error ? <p className="error-text about-export-message">{error}</p> : null}
      {status ? <p className="muted about-export-message">{status}</p> : null}
    </div>
  );
}

export function AboutKnowledgePanel({ page }: { page: AboutGuidePage }) {
  return (
    <section className="panel product-info-panel">
      <div className="about-product-layout">
        {page === "overview" ? (
          <>
            <article className="about-product-summary">
              <div className="about-summary-heading">
                <h3>What the product does</h3>
                <AboutDocumentationExport />
              </div>
              <p>
                LighthousePM turns Jira release and sprint activity into deterministic delivery metrics, release
                readiness signals, and recommended actions. It is built for teams that need a clear view of blockers,
                quality risk, scope movement, flow health, and confidence trends before release decisions are made.
              </p>
            </article>
            <div className="product-info-grid">
              <article className="product-info-card">
                <span className="product-info-icon nav-releases" aria-hidden="true" />
                <h3>Release Intelligence</h3>
                <p>Shows confidence, readiness, critical risks, warnings, tickets, and release-level trend history.</p>
              </article>
              <article className="product-info-card">
                <span className="product-info-icon nav-sprints" aria-hidden="true" />
                <h3>Sprint Intelligence</h3>
                <p>Tracks progress alignment, active work, blockers, sprint-created bugs, unfinished closed-sprint work, and predictability.</p>
              </article>
              <article className="product-info-card">
                <span className="product-info-icon nav-overview" aria-hidden="true" />
                <h3>Explainable Signals</h3>
                <p>Every confidence signal is tied to explicit metrics, thresholds, reasons, and risk contribution.</p>
              </article>
              <article className="product-info-card">
                <span className="product-info-icon nav-reports" aria-hidden="true" />
                <h3>Operational Evidence</h3>
                <p>Reports preserve the charts, aging detail, comparison data, and ticket context behind each decision.</p>
              </article>
            </div>
            <article className="about-product-summary">
              <h3>Overview</h3>
              <p>
                The Overview section is the executive decision view of LighthousePM. It gives a Head of PO, CEO, or Head
                of PM a single place to understand whether the selected release is still a responsible business
                commitment, what is creating delivery or quality risk, and which actions should be taken first.
              </p>
            </article>
            <AboutGuideGrid sections={aboutOverviewSections} />
          </>
        ) : null}
        {page === "releases" ? (
          <>
            <article className="about-product-summary">
              <h3>Releases</h3>
              <p>
                The Releases area explains release readiness in two layers: Command Center for current operational
                decisions, and Reports &amp; Evidence for the historical proof behind those decisions.
              </p>
            </article>
            <AboutGuideGrid sections={aboutReleaseSections} />
            <article className="about-product-summary">
              <h3>Release metric definitions</h3>
              <p>
                These metrics explain the evidence behind release confidence. They help leadership separate delivery
                progress, quality risk, flow health, scope movement, and blocking risk before a release decision is made.
              </p>
            </article>
            <AboutGuideGrid sections={aboutReleaseMetricSections} />
          </>
        ) : null}
        {page === "sprints" ? (
          <>
            <article className="about-product-summary">
              <h3>Sprints</h3>
              <p>
                The Sprints area explains whether the active sprint supports the release plan. Sprint Intelligence focuses
                on current delivery health, while Reports &amp; Evidence preserves trends, reliability, and ticket-level
                context.
              </p>
            </article>
            <AboutGuideGrid sections={aboutSprintSections} />
            <article className="about-product-summary">
              <h3>Sprint metric definitions</h3>
              <p>
                These metrics explain whether the sprint currently supports the release plan. They connect current scope,
                progress, quality, flow, blockers, scope stability, and delivery confidence to concrete sprint decisions.
              </p>
            </article>
            <AboutGuideGrid sections={aboutSprintMetricSections} />
          </>
        ) : null}
      </div>
    </section>
  );
}
