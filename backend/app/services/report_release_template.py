from collections.abc import Mapping
from datetime import datetime

from app.models import MetricSnapshot
from app.schemas.availability import MetricAvailability
from app.services.report_data_preparation import (
    PreparedReleaseReportData,
    PreparedSnapshotComparison,
)
from app.services.report_document_models import (
    ChartSpec,
    PdfTheme,
    ReportDepth,
    ReportDocument,
    ReportSection,
)
from app.services.report_theme import PDFThemeProvider
from app.services.report_template_helpers import (
    _release_confidence_for_report,
    _ruleset_label,
    _stored_release_confidence_artifacts,
    breakdown_rows,
    confidence_band,
    decision_recommendation_lines,
    driver_rows,
    format_datetime,
    format_delta,
    format_number,
    format_report_metric_value,
    format_short_datetime,
    gate_rows,
    recommendation_bullets,
    release_metric_rows,
    release_top_risk_bullets,
    report_metric_label,
)


class ReleaseReportTemplate:
    def __init__(self, theme: PdfTheme | None = None) -> None:
        self.theme = theme or PDFThemeProvider().theme()

    def build_release_document(
        self,
        data: PreparedReleaseReportData,
        depth: ReportDepth,
        generated_at: datetime,
    ) -> ReportDocument:
        if depth == "summary":
            sections = self._release_summary_sections(data)
            title = f"Release Summary Report: {data.release.name}"
        else:
            sections = self._release_sections(data)
            title = f"Release Report: {data.release.name}"
        return ReportDocument(
            title=title,
            subtitle=(
                f"{data.release.project_key} | {data.release.release_id} | "
                f"{data.release.status or 'Unknown status'}"
            ),
            entity_id=data.release.release_id,
            generated_at=generated_at,
            version=data.version,
            sections=sections,
        )

    def _release_sections(
        self,
        data: PreparedReleaseReportData,
    ) -> list[ReportSection]:
        release = data.release
        snapshot = data.snapshot
        snapshots = data.snapshots
        readiness = data.readiness
        confidence_breakdown, biggest_driver = _stored_release_confidence_artifacts(
            snapshot
        )
        release_availability = data.availability
        if not release_availability.context.has_tickets:
            confidence_breakdown = None
            biggest_driver = None
        outlook_section = self.outlook_section(data.outlook)
        risk_aging_section = self.risk_aging_section(
            snapshot,
            data.risk_aging_evidence,
        )
        return [
            ReportSection(
                "Executive Summary",
                lines=[
                    readiness.get("summary")
                    or "Release report generated from deterministic LighthousePM snapshots."
                ],
                rows=[
                    ("Release", release.name),
                    ("Project", release.project_key),
                    ("Status", release.status or "Unknown"),
                    ("Release date", format_datetime(release.release_date)),
                    (
                        "Latest snapshot",
                        format_datetime(snapshot.snapshot_at if snapshot else None),
                    ),
                    ("Ruleset", _ruleset_label(snapshot)),
                    (
                        "Signal",
                        str(
                            readiness.get("status_label")
                            or readiness.get("signal")
                            or "Not computed"
                        ),
                    ),
                    (
                        report_metric_label("release.confidence_score")
                        .removeprefix("Release ")
                        .capitalize(),
                        format_report_metric_value(
                            "release.confidence_score",
                            readiness.get("confidence_score"),
                        ),
                    ),
                ],
            ),
            outlook_section,
            risk_aging_section,
            ReportSection(
                "Confidence Breakdown", rows=breakdown_rows(confidence_breakdown)
            ),
            ReportSection(
                "Confidence Trend",
                charts=[
                    ChartSpec(
                        title="Confidence Score",
                        kind="line",
                        points=[
                            (
                                format_short_datetime(item.snapshot_at),
                                _release_confidence_for_report(
                                    item, release_availability
                                ),
                            )
                            for item in snapshots
                        ],
                        color=self.theme.metric_colors["sprintConfidence"].rgb,
                        y_max=100,
                        value_suffix="%",
                    ),
                    ChartSpec(
                        title="Readiness %",
                        kind="line",
                        points=[
                            (
                                format_short_datetime(item.snapshot_at),
                                item_readiness.get("readiness_pct"),
                            )
                            for item, item_readiness in zip(
                                snapshots,
                                data.readiness_history,
                            )
                        ],
                        color=self.theme.metric_colors["readiness"].rgb,
                        y_max=100,
                        value_suffix="%",
                    ),
                ],
            ),
            self.snapshot_changes(
                release.release_id,
                snapshots,
                data.snapshot_comparison,
            ),
            ReportSection("Biggest Driver", rows=driver_rows(biggest_driver)),
            ReportSection(
                "Risk Analysis",
                bullets=[
                    *[str(reason) for reason in readiness.get("reasons", [])],
                    *[
                        risk.get("message", "")
                        for risk in readiness.get("critical_risks", [])
                        if isinstance(risk, dict)
                    ],
                    *[
                        risk.get("message", "")
                        for risk in readiness.get("warnings", [])
                        if isinstance(risk, dict)
                    ],
                ]
                or ["No active release risks found in the latest computed signal."],
            ),
            ReportSection(
                "Recommended Actions",
                bullets=recommendation_bullets(data.recommendations),
            ),
            ReportSection(
                "Release Gates", rows=gate_rows(readiness.get("release_gates", []))
            ),
            ReportSection(
                "Evidence Metrics",
                rows=release_metric_rows(snapshot, release_availability),
            ),
            ReportSection(
                "Historical Trends",
                charts=self.historical_charts(
                    release.release_id, snapshots, release_availability
                ),
            ),
        ]

    def _release_summary_sections(
        self,
        data: PreparedReleaseReportData,
    ) -> list[ReportSection]:
        release = data.release
        snapshot = data.snapshot
        readiness = data.readiness
        confidence_score = readiness.get("confidence_score")
        confidence_breakdown, biggest_driver = _stored_release_confidence_artifacts(
            snapshot
        )
        release_availability = data.availability
        if not release_availability.context.has_tickets:
            confidence_breakdown = None
            biggest_driver = None
        outlook_section = self.outlook_section(data.outlook)
        risk_aging_section = self.risk_aging_section(
            snapshot,
            data.risk_aging_evidence,
        )
        return [
            ReportSection(
                "Executive Summary",
                lines=[
                    readiness.get("summary")
                    or "Release summary generated from deterministic LighthousePM metrics."
                ],
                rows=[
                    ("Release", release.name),
                    ("Project", release.project_key),
                    ("Status", release.status or "Unknown"),
                    ("Release date", format_datetime(release.release_date)),
                    (
                        "Latest snapshot",
                        format_datetime(snapshot.snapshot_at if snapshot else None),
                    ),
                    ("Ruleset", _ruleset_label(snapshot)),
                ],
            ),
            outlook_section,
            risk_aging_section,
            ReportSection(
                "Confidence Score",
                rows=[
                    (
                        "Score",
                        format_report_metric_value(
                            "release.confidence_score", confidence_score
                        ),
                    ),
                    (
                        "Signal",
                        str(
                            readiness.get("status_label")
                            or readiness.get("signal")
                            or "Not computed"
                        ),
                    ),
                    ("Band", confidence_band(confidence_score)),
                ],
            ),
            ReportSection(
                "Confidence Breakdown", rows=breakdown_rows(confidence_breakdown)
            ),
            ReportSection("Biggest Driver", rows=driver_rows(biggest_driver)),
            ReportSection(
                "Top Risks", bullets=release_top_risk_bullets(readiness, limit=3)
            ),
            ReportSection(
                "Top Recommendations",
                bullets=recommendation_bullets(data.recommendations, limit=3),
            ),
            ReportSection(
                "Decision Recommendation",
                lines=decision_recommendation_lines(readiness),
            ),
        ]

    def outlook_section(
        self,
        outlook: Mapping[str, object],
    ) -> ReportSection:
        active_conditions = outlook["active_conditions"]
        return ReportSection(
            "Release Outlook",
            lines=[str(outlook["disclaimer"])],
            rows=[
                ("Outlook", str(outlook["label"])),
                ("Final signal", str(outlook["signal"] or "Not computed")),
                (
                    f"Current {report_metric_label('release.confidence_score').removeprefix('Release ').lower()}",
                    format_report_metric_value(
                        "release.confidence_score", outlook["confidence_score"]
                    ),
                ),
                (
                    "Passed release gates",
                    format_report_metric_value(
                        "release.gates_passed_count", outlook["passed_gate_count"]
                    ),
                ),
                (
                    "Failed release gates",
                    format_report_metric_value(
                        "release.gates_passed_count", outlook["failed_gate_count"]
                    ),
                ),
                (
                    "24-hour confidence change",
                    format_delta(float(outlook["confidence_change_24h"]))
                    if isinstance(outlook["confidence_change_24h"], int | float)
                    else "N/A",
                ),
                ("Calendar days remaining", format_number(outlook["days_remaining"])),
            ],
            bullets=(
                [
                    str(item.get("message", ""))
                    for item in active_conditions
                    if isinstance(item, dict) and item.get("message")
                ]
                or ["No active hard RED or YELLOW conditions."]
            ),
        )

    def risk_aging_section(
        self,
        snapshot: MetricSnapshot | None,
        evidence: Mapping[str, object],
    ) -> ReportSection:
        if snapshot is None:
            return ReportSection(
                "Risk Aging Evidence", lines=["No release snapshot is available."]
            )
        if not evidence:
            return ReportSection(
                "Risk Aging Evidence",
                lines=["Stored risk-aging evidence is unavailable for this result."],
            )
        rows: list[tuple[str, str]] = [
            ("Snapshot boundary", format_datetime(snapshot.snapshot_at))
        ]
        bullets: list[str] = []
        for key, label in (
            ("blockers", "Blockers"),
            ("high_severity_bugs", "High-severity bugs"),
        ):
            group = evidence.get(key, {})
            if not isinstance(group, dict):
                continue
            rows.extend(
                [
                    (f"{label} active", format_number(group.get("count"))),
                    (f"{label} known age", format_number(group.get("known_count"))),
                    (f"{label} unknown age", format_number(group.get("unknown_count"))),
                    (
                        f"{label} oldest risk age days",
                        format_number(group.get("oldest_age_days")),
                    ),
                    (
                        f"{label} average risk age days",
                        format_number(group.get("average_age_days")),
                    ),
                ]
            )
            for ticket in group.get("tickets", []):
                if not isinstance(ticket, dict):
                    continue
                bullets.append(
                    f"{ticket.get('key')}: issue age {format_number(ticket.get('issue_age_days'))} days; "
                    f"risk age {format_number(ticket.get('age_days'))} days; "
                    f"Jira created {ticket.get('jira_created_at') or 'N/A'}; "
                    f"risk start {ticket.get('risk_started_at') or 'N/A'}; "
                    f"source {ticket.get('risk_start_source_field') or 'N/A'}; "
                    f"history complete {ticket.get('history_complete')}; "
                    f"{ticket.get('explanation') or 'Risk start proven from stored Jira evidence.'}"
                )
        return ReportSection(
            "Risk Aging Evidence",
            rows=rows,
            bullets=bullets
            or ["No active blocker or high-severity-bug aging evidence."],
        )

    def snapshot_changes(
        self,
        release_id: str,
        snapshots: tuple[MetricSnapshot, ...],
        comparison: PreparedSnapshotComparison | None,
    ) -> ReportSection:
        if len(snapshots) < 2:
            return ReportSection(
                "Snapshot Changes", lines=["No baseline snapshot is available yet."]
            )
        if snapshots[-1].ruleset_version != snapshots[-2].ruleset_version:
            return ReportSection(
                "Snapshot Changes",
                lines=[
                    "Snapshot comparison unavailable because ruleset versions differ."
                ],
                rows=[
                    ("Current ruleset", _ruleset_label(snapshots[-1])),
                    ("Baseline ruleset", _ruleset_label(snapshots[-2])),
                ],
            )
        if snapshots[-1].ruleset_version == 0:
            return ReportSection(
                "Snapshot Changes",
                lines=[
                    "Derived legacy release confidence is unavailable because it was not stored at calculation time."
                ],
            )
        if comparison is None:
            return ReportSection(
                "Snapshot Changes",
                lines=["Snapshot comparison is unavailable for this result."],
            )
        return ReportSection(
            "Snapshot Changes",
            rows=[
                ("Current snapshot", format_datetime(snapshots[-1].snapshot_at)),
                ("Baseline snapshot", format_datetime(snapshots[-2].snapshot_at)),
                ("Confidence delta", format_delta(comparison.confidence_delta)),
                ("Primary driver", comparison.primary_driver),
                ("Entity", release_id),
            ],
        )

    def historical_charts(
        self,
        release_id: str,
        snapshots: list[MetricSnapshot],
        release_availability: MetricAvailability | None = None,
    ) -> list[ChartSpec]:
        return [
            ChartSpec(
                title="Historical Confidence",
                kind="line",
                points=[
                    (
                        format_short_datetime(snapshot.snapshot_at),
                        _release_confidence_for_report(snapshot, release_availability),
                    )
                    for snapshot in snapshots
                ],
                color=self.theme.metric_colors["sprintConfidence"].rgb,
                y_max=100,
                value_suffix="%",
            ),
            ChartSpec(
                title="Historical Release Gates Passed",
                kind="line",
                points=[
                    (
                        format_short_datetime(snapshot.snapshot_at),
                        self.gate_passed_count(
                            release_id, snapshot, release_availability
                        ),
                    )
                    for snapshot in snapshots
                ],
                color=self.theme.metric_colors["gatesPassed"].rgb,
            ),
            ChartSpec(
                title="Historical Open Blockers",
                kind="bar",
                points=[
                    (
                        format_short_datetime(snapshot.snapshot_at),
                        snapshot.open_blockers,
                    )
                    for snapshot in snapshots
                ],
                color=self.theme.metric_colors["blockers"].rgb,
            ),
            ChartSpec(
                title="Historical High-Severity Bugs",
                kind="bar",
                points=[
                    (
                        format_short_datetime(snapshot.snapshot_at),
                        snapshot.open_high_severity_bugs,
                    )
                    for snapshot in snapshots
                ],
                color=self.theme.metric_colors["bugs"].rgb,
            ),
            ChartSpec(
                title="Historical Scope Completed",
                kind="line",
                points=[
                    (
                        format_short_datetime(snapshot.snapshot_at),
                        snapshot.scope_completed_pct,
                    )
                    for snapshot in snapshots
                ],
                color=self.theme.metric_colors["scopeCompleted"].rgb,
                y_max=100,
                value_suffix="%",
            ),
            ChartSpec(
                title="Historical Scope Churn",
                kind="line",
                points=[
                    (
                        format_short_datetime(snapshot.snapshot_at),
                        snapshot.scope_churn_7d_pct,
                    )
                    for snapshot in snapshots
                ],
                color=self.theme.metric_colors["scopeChurn"].rgb,
                value_suffix="%",
            ),
            ChartSpec(
                title="Historical Median Cycle Time",
                kind="line",
                points=[
                    (
                        format_short_datetime(snapshot.snapshot_at),
                        snapshot.median_cycle_time_days,
                    )
                    for snapshot in snapshots
                ],
                color=self.theme.metric_colors["cycleTime"].rgb,
            ),
            ChartSpec(
                title="Historical Reopen Events per 100 Eligible Tickets",
                kind="line",
                points=[
                    (
                        format_short_datetime(snapshot.snapshot_at),
                        snapshot.reopen_rate_pct,
                    )
                    for snapshot in snapshots
                ],
                color=self.theme.metric_colors["reopenRate"].rgb,
                value_suffix="%",
            ),
        ]

    def gate_passed_count(
        self,
        release_id: str,
        snapshot: MetricSnapshot,
        release_availability: MetricAvailability | None = None,
    ) -> int | None:
        _ = release_id
        if (
            release_availability is not None
            and not release_availability.context.has_tickets
        ):
            return None
        outputs = (snapshot.calculation_provenance or {}).get("component_outputs", {})
        gates = outputs.get("release_gates", []) if isinstance(outputs, dict) else []
        if not isinstance(gates, list):
            return None
        return sum(
            1 for gate in gates if isinstance(gate, dict) and gate.get("passed") is True
        )
