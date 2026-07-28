import { useState } from "react";

import { apiClient } from "../api/client";
import type { MetricScope } from "../api/types";
import { savePdfBlob } from "../components/ReportExportActions";
import { useMetricCatalog } from "../MetricCatalogContext";
import { metricDefinition, type MetricCatalogView } from "../metricCatalog";

type AboutGuidePage = "overview" | "releases" | "sprints";

type AboutGuideSection = {
  title?: string;
  metric?: {
    scope: MetricScope;
    apiField: string;
  };
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
    metric: { scope: "release", apiField: "scope_completed_pct" },
    description:
      "Shows the percentage of current release tickets whose status is configured as done. It is ticket-based and does not use story points. If any current release ticket has no status, the percentage is withheld and marked Partial with the affected Jira keys. Empty release scope is Not computed rather than zero.",
    questions: [
      "Is enough release scope complete for the planned date?",
      "Is delivery progress aligned with the business expectation?",
      "Do we need to reduce scope or increase delivery focus?",
    ],
  },
  {
    metric: { scope: "release", apiField: "completed_tickets" },
    description:
      "Counts current release tickets whose status is configured as done. If current release tickets are missing status, the displayed count is a confirmed minimum and is marked Partial. Empty release scope is Not computed.",
    questions: [
      "How much work has actually landed?",
      "Is progress supported by completed Jira items?",
      "Can we explain release progress with ticket-level evidence?",
    ],
  },
  {
    metric: { scope: "release", apiField: "scope_churn_7d_pct" },
    description:
      "Measures release scope addition and removal events over the seven days ending at the stored snapshot time. Every distinct transition is counted, including repeated removal and re-addition of the same ticket. The percentage compares the total event count against distinct observed scope and may exceed 100%. Incomplete project changelog ingestion withholds the percentage while confirmed event counts remain Partial evidence.",
    questions: [
      "Is the release commitment stable enough to govern?",
      "Are new requests or removals changing the delivery promise late?",
      "Should leadership freeze scope or defer non-critical work?",
    ],
  },
  {
    metric: { scope: "release", apiField: "scope_added_7d_count" },
    description:
      "Counts distinct addition events in the recent seven-day scope window. Adding the same ticket more than once through separate transitions increases the count each time. Incomplete project changelog ingestion leaves this as a Partial confirmed minimum.",
    questions: [
      "What new work has entered the release recently?",
      "Is added scope putting the date or quality bar at risk?",
      "Do added items need executive approval or deferral?",
    ],
  },
  {
    metric: { scope: "release", apiField: "scope_removed_7d_count" },
    description:
      "Counts distinct removal events in the recent seven-day scope window. Removing the same ticket more than once through separate transitions increases the count each time. Incomplete project changelog ingestion leaves this as a Partial confirmed minimum.",
    questions: [
      "Are we protecting the release by deliberately reducing scope?",
      "Are removals changing stakeholder expectations?",
      "Do we need to communicate a scope trade-off?",
    ],
  },
  {
    metric: { scope: "release", apiField: "open_high_severity_bugs" },
    description:
      "Counts unresolved high-severity defects in the release. Missing issue type, severity, or status can make the count a Partial confirmed minimum. Empty scope is Not computed and does not present zero as healthy evidence.",
    questions: [
      "Is quality acceptable for release approval?",
      "Which critical defects still need management attention?",
      "Should the team prioritize quality over new scope?",
    ],
  },
  {
    metric: { scope: "release", apiField: "reopen_rate_pct" },
    description:
      "Counts every transition from done back to a non-done status per 100 eligible tickets. The same ticket is counted for every distinct reopen event, so the value can exceed 100. If relevant current status or Jira history is incomplete, confirmed event and eligible-ticket counts remain evidence but the percentage is withheld as Partial.",
    questions: [
      "Is completed work staying done?",
      "Are acceptance or quality standards creating rework?",
      "Do we need tighter validation before release approval?",
    ],
  },
  {
    metric: { scope: "release", apiField: "median_cycle_time_days" },
    description:
      "Shows the median duration from each eligible ticket's earliest transition into a configured in-progress status to its first later transition into a configured done status. If a potentially eligible ticket has missing status or incomplete history, the median is withheld as Partial. Complete evidence with no valid transition pair is Not computed.",
    questions: [
      "Is work flowing fast enough to protect the release date?",
      "Are tickets spending too long in progress or review?",
      "Do we need to remove process, dependency, or capacity bottlenecks?",
    ],
  },
  {
    metric: { scope: "release", apiField: "open_blockers" },
    description:
      "Counts unresolved blocking issues in the release. Missing status or insufficient blocker-classification evidence can make the count a Partial confirmed minimum. Empty scope is Not computed.",
    questions: [
      "What is stopping the release from moving forward?",
      "Which blockers require escalation or ownership decisions?",
      "Can the release proceed while these blockers remain open?",
    ],
  },
  {
    metric: { scope: "release", apiField: "confidence_score" },
    description:
      "Subtracts approved weighted risk points from 100 and should always be read with its stored drivers. When Jira classification inputs are incomplete, the score is withheld. A confirmed hard-red risk remains RED; otherwise the release is Inconclusive until the missing evidence is completed and metrics are recomputed.",
    questions: [
      "What is the current confidence level for this release?",
      "Is the release improving, stable, or deteriorating?",
      "Which underlying metrics explain the score?",
    ],
  },
  {
    title: "Derived view: Readiness and gates",
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
    metric: { scope: "sprint", apiField: "committed_scope" },
    description:
      "Counts distinct tickets currently linked to the sprint at snapshot time. The API retains the field name committed_scope for compatibility, but this metric describes current membership and does not reconstruct the sprint-start commitment. An empty current scope is shown as unavailable rather than zero.",
    questions: [
      "How many tickets are currently in the sprint?",
      "Which tickets define the scope measured by the current snapshot?",
      "Is the current Jira sprint membership complete and up to date?",
    ],
  },
  {
    metric: { scope: "sprint", apiField: "completed_scope_pct" },
    description:
      "Shows the percentage of current sprint tickets whose current status is configured as done. It is ticket-based and does not use story points. Empty scope is unavailable, and missing ticket statuses make the percentage partial with the affected Jira keys identified.",
    questions: [
      "Is the sprint progressing fast enough?",
      "How much of the current ticket scope is already finished?",
      "Do we need to narrow focus to complete remaining work?",
    ],
  },
  {
    metric: { scope: "sprint", apiField: "scope_creep_pct" },
    description:
      "Shows sprint addition and removal events after the sprint starts per 100 initial-commitment tickets. Re-adding a previously removed ticket counts as another event, so the percentage may exceed 100%. Missing sprint start or incomplete project membership history makes the result unavailable; zero initial commitment is Not computed.",
    questions: [
      "Is sprint scope stable after planning?",
      "Are new requests interrupting the sprint commitment?",
      "Should added work move to the next planning cycle?",
    ],
  },
  {
    title: "Derived view: Velocity health",
    description:
      "Compares current completed work with the eligible historical velocity baseline used by delivery confidence. It describes current calculation inputs and does not predict future output.",
    questions: [
      "Is the team delivering at a healthy pace?",
      "Is current output below recent sprint history?",
      "Do capacity or priority decisions need attention?",
    ],
  },
  {
    title: "Derived view: Historical commitment reliability",
    description:
      "Shows how recent closed sprints compare committed and completed work when the required stored evidence is available. It describes historical consistency and is not a probability for the current sprint.",
    questions: [
      "Can we trust sprint commitments based on recent history?",
      "Is the team becoming more or less predictable?",
      "Should planning assumptions be adjusted?",
    ],
  },
  {
    metric: { scope: "sprint", apiField: "open_high_severity_bugs" },
    description:
      "Counts unresolved serious defects inside the sprint. Missing issue type, severity, or status can make this a Partial confirmed minimum. Empty current sprint scope is Not computed.",
    questions: [
      "Is the sprint producing or carrying critical quality risk?",
      "Should defect resolution take priority over feature work?",
      "Will sprint quality issues threaten release readiness?",
    ],
  },
  {
    metric: { scope: "sprint", apiField: "bugs_created_during_sprint" },
    description:
      "Counts current-sprint bugs whose Jira creation time falls inside the inclusive sprint window. Missing sprint start makes the metric unavailable, while missing Jira creation time makes the count Partial and exposes the affected Jira keys. Local database insertion time is never substituted.",
    questions: [
      "Is new defect work consuming sprint capacity?",
      "Are quality issues emerging during execution?",
      "Do we need to protect time for stabilization?",
    ],
  },
  {
    metric: { scope: "sprint", apiField: "reopen_rate_pct" },
    description:
      "Counts every transition from done back to a non-done status per 100 eligible sprint tickets. The same ticket is counted for every distinct reopen event, so the value can exceed 100. Incomplete status or history evidence withholds the percentage as Partial while retaining confirmed event evidence.",
    questions: [
      "Is sprint work really complete when marked done?",
      "Are acceptance criteria or quality checks clear enough?",
      "Is rework putting the sprint goal at risk?",
    ],
  },
  {
    metric: { scope: "sprint", apiField: "median_cycle_time_days" },
    description:
      "Shows the median first valid in-progress-to-done duration for eligible current-sprint tickets. Missing status or incomplete history withholds the median as Partial; complete evidence with no valid pair is Not computed.",
    questions: [
      "Is sprint work moving through the system fast enough?",
      "Where might work be stuck?",
      "Do we need to address review, dependency, or handoff bottlenecks?",
    ],
  },
  {
    metric: { scope: "sprint", apiField: "open_blockers" },
    description:
      "Counts unresolved blockers in the sprint. Missing status or incomplete blocker classification can make this a Partial confirmed minimum. Empty current sprint scope is Not computed.",
    questions: [
      "What is preventing sprint work from progressing?",
      "Which blockers need ownership or escalation?",
      "Can the team still meet the sprint goal with these blockers open?",
    ],
  },
  {
    metric: { scope: "sprint", apiField: "rollover_count" },
    description:
      "Counts tickets that remain in the current membership of a closed sprint and have a known non-done status. It does not prove that a ticket entered another sprint. Active, future, or unknown-state sprints are Not applicable; empty closed-sprint scope is Not computed; missing statuses make the count a Partial confirmed minimum.",
    questions: [
      "How many currently assigned tickets are unfinished after the sprint closed?",
      "Which known unfinished tickets need follow-up?",
      "Are any ticket statuses missing, making the count partial?",
    ],
  },
  {
    metric: { scope: "sprint", apiField: "workload_concentration_pct" },
    description:
      "Shows the top assignee's share of included active sprint story points using configured done-status rules. Below required story-point coverage the result is Inconclusive; partial coverage excludes unpointed active tickets and identifies them. Missing stable assignee identity can make the result Partial. No active work is Not applicable, a zero-point denominator is Not computed, and catalog-defined severity bands apply to the stored result reused by recommendations, reports, and the dashboard.",
    questions: [
      "Is too much critical work dependent on one person?",
      "Should work be rebalanced to reduce delivery risk?",
      "Is capacity hidden behind a single overloaded owner?",
      "Is the result partial or inconclusive because required Jira evidence is missing?",
    ],
  },
  {
    title: "Derived view: Sprint work state",
    description:
      "Condenses current sprint scope, in-progress, not-started, done, and applicable unfinished closed-sprint work into one scan-friendly view of sprint execution.",
    questions: [
      "How is sprint work distributed across states?",
      "Is too much work not started or still active late in the sprint?",
      "Does the sprint state support the delivery-confidence score?",
    ],
  },
  {
    metric: { scope: "sprint", apiField: "delivery_confidence_score" },
    description:
      "Combines progress alignment, velocity fit, blocker health, and scope stability into one sprint score. Empty scope is Not computed and story-point coverage below 50% is Inconclusive. From 50% to below complete coverage, the score is Partial and point-based components use only pointed tickets. Required status, blocker-classification, duration, and project sprint-history evidence must also be complete or the result is Inconclusive.",
    questions: [
      "Does current sprint evidence support its delivery plan?",
      "Which confidence component is pulling the sprint down?",
      "Is the result Inconclusive because required evidence is missing?",
    ],
  },
  {
    title: "Delivery-confidence component: Progress alignment",
    description:
      "Compares completed scope with elapsed sprint time. It requires valid sprint start and end times; missing or invalid duration makes the component unavailable rather than healthy.",
    questions: [
      "Is progress keeping pace with time elapsed?",
      "Is the sprint behind even if some work is complete?",
      "Should the team focus on finishing rather than starting?",
    ],
  },
  {
    title: "Delivery-confidence component: Velocity fit",
    description:
      "Checks whether remaining sprint work fits the team's historical delivery capacity. It uses valid sprint duration and never substitutes a healthy time or capacity fallback when duration is unavailable.",
    questions: [
      "Does the remaining work fit the team's documented historical capacity?",
      "Is the sprint plan larger than recent delivery capacity?",
      "Do we need a scope or staffing decision?",
    ],
  },
  {
    title: "Delivery-confidence component: Scope stability",
    description:
      "Scores how stable sprint scope has been since the initial commitment. It requires a sprint start and complete sprint-membership history across synchronized project tickets; otherwise the component and delivery confidence are unavailable.",
    questions: [
      "Is the team executing a stable plan?",
      "Are scope changes weakening confidence?",
      "Should leadership protect the sprint from late additions?",
    ],
  },
];

function aboutGuideTitle(
  section: AboutGuideSection,
  catalog: MetricCatalogView,
) {
  if (section.metric) {
    return `Metric: ${metricDefinition(
      catalog,
      section.metric.scope,
      section.metric.apiField,
    ).label}`;
  }
  return section.title ?? "Guide";
}

function AboutGuideCard({
  section,
  catalog,
}: {
  section: AboutGuideSection;
  catalog: MetricCatalogView;
}) {
  const title = aboutGuideTitle(section, catalog);
  return (
    <article className="about-guide-card">
      <h3>{title}</h3>
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
  const catalog = useMetricCatalog();
  return (
    <div className="about-guide-grid" aria-label="About guide sections">
      {sections.map((section) => (
        <AboutGuideCard
          key={section.title ?? `${section.metric?.scope}.${section.metric?.apiField}`}
          section={section}
          catalog={catalog}
        />
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
