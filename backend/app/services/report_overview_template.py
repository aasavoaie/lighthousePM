from collections.abc import Sequence
from datetime import datetime

from app.models import MetricSnapshot, SprintMetricSnapshot
from app.schemas.availability import MetricAvailability
from app.services.report_data_preparation import (
    PreparedOverviewReportData,
    PreparedPortfolioData,
)
from app.services.report_document_models import (
    ChartSpec,
    PdfTheme,
    ReportDocument,
    ReportSection,
)
from app.services.report_release_template import ReleaseReportTemplate
from app.services.report_theme import PDFThemeProvider
from app.services.report_template_helpers import (
    _first_last_delta,
    _overview_release_snapshot_label,
    _overview_sprint_snapshot_label,
    _release_confidence_for_report,
    _ruleset_label,
    confidence_band,
    format_datetime,
    format_delta,
    format_number,
    format_report_metric_value,
    format_short_datetime,
    overview_health_rows,
    overview_recommendation_bullets,
    overview_risk_bullets,
    overview_signal_rows,
    overview_sprint_metric_rows,
    release_metric_rows,
    report_metric_label,
)


class OverviewReportTemplate:
    def __init__(
        self,
        theme: PdfTheme | None = None,
        release_template: ReleaseReportTemplate | None = None,
    ) -> None:
        self.theme = theme or PDFThemeProvider().theme()
        self.release_template = release_template or ReleaseReportTemplate(
            theme=self.theme
        )

    def build_overview_document(
        self,
        data: PreparedOverviewReportData,
        generated_at: datetime,
    ) -> ReportDocument:
        release = data.release_data.release
        return ReportDocument(
            title=f"Overview Dashboard Report: {release.name}",
            subtitle=f"{release.project_key} | {release.release_id} | {release.status or 'Unknown status'}",
            entity_id=release.release_id,
            generated_at=generated_at,
            version=data.version,
            sections=self._overview_sections(data),
        )

    def _overview_sections(
        self,
        data: PreparedOverviewReportData,
    ) -> list[ReportSection]:
        release_data = data.release_data
        release = release_data.release
        snapshot = release_data.snapshot
        snapshots = release_data.snapshots
        readiness = release_data.readiness
        release_availability = release_data.availability
        sprint = data.sprint
        sprint_snapshot = data.sprint_snapshot
        sprint_snapshots = data.sprint_snapshots
        sprint_has_story_points = data.sprint_has_story_points
        sprint_delivery_confidence = (
            sprint_snapshot.delivery_confidence_score
            if sprint_snapshot and sprint_has_story_points
            else None
        )
        confidence_score = readiness.get("confidence_score")
        confidence_delta = _first_last_delta(
            [
                _release_confidence_for_report(item, release_availability)
                for item in snapshots
            ]
        )
        outlook_section = self.release_template.outlook_section(release_data.outlook)
        risk_aging_section = self.release_template.risk_aging_section(
            snapshot,
            release_data.risk_aging_evidence,
        )
        return [
            ReportSection(
                "Executive Summary",
                lines=[
                    str(
                        readiness.get("summary")
                        or "Overview dashboard exported from deterministic LighthousePM data."
                    )
                ],
                rows=[
                    ("Release", release.name),
                    ("Project", release.project_key),
                    ("Release status", release.status or "Unknown"),
                    ("Release date", format_datetime(release.release_date)),
                    ("Current sprint", sprint.name if sprint else "No active sprint"),
                    (
                        "Latest release snapshot",
                        _overview_release_snapshot_label(snapshot),
                    ),
                    ("Release ruleset", _ruleset_label(snapshot)),
                    (
                        "Latest sprint snapshot",
                        _overview_sprint_snapshot_label(sprint, sprint_snapshot),
                    ),
                    ("Sprint ruleset", _ruleset_label(sprint_snapshot)),
                ],
            ),
            outlook_section,
            risk_aging_section,
            ReportSection(
                "Project Portfolio Metrics",
                rows=self._portfolio_metric_rows(data.portfolio),
            ),
            ReportSection(
                "Release Metrics",
                rows=release_metric_rows(snapshot, release_availability),
            ),
            ReportSection(
                "Sprint Metrics",
                rows=overview_sprint_metric_rows(
                    sprint,
                    sprint_snapshot,
                    sprint_has_story_points,
                    data.sprint_availability,
                ),
            ),
            ReportSection(
                "Confidence Metrics",
                rows=[
                    (
                        report_metric_label("release.confidence_score"),
                        format_report_metric_value(
                            "release.confidence_score", confidence_score
                        ),
                    ),
                    ("Release confidence band", confidence_band(confidence_score)),
                    (
                        "Confidence delta",
                        format_delta(confidence_delta)
                        if confidence_delta is not None
                        else "N/A",
                    ),
                    (
                        report_metric_label("release.readiness_pct"),
                        format_report_metric_value(
                            "release.readiness_pct",
                            readiness.get("readiness_pct"),
                        ),
                    ),
                    (
                        f"Sprint {report_metric_label('sprint.delivery_confidence_score').lower()}",
                        format_report_metric_value(
                            "sprint.delivery_confidence_score",
                            sprint_delivery_confidence,
                        ),
                    ),
                    (
                        "Sprint confidence band",
                        confidence_band(sprint_delivery_confidence),
                    ),
                ],
            ),
            ReportSection(
                "Risk Indicators",
                bullets=overview_risk_bullets(readiness, snapshot, sprint_snapshot),
            ),
            ReportSection("Signals", rows=overview_signal_rows(readiness)),
            ReportSection(
                "Trends",
                charts=self._overview_charts(
                    snapshots,
                    sprint_snapshots,
                    sprint_has_story_points,
                    release_availability,
                ),
            ),
            ReportSection(
                "Health Indicators",
                rows=overview_health_rows(
                    readiness, snapshot, sprint_snapshot, sprint_has_story_points
                ),
            ),
            ReportSection(
                "Recommendations",
                bullets=overview_recommendation_bullets(
                    release_data.recommendations,
                    data.sprint_recommendations,
                ),
            ),
        ]

    def _portfolio_metric_rows(
        self,
        portfolio: PreparedPortfolioData,
    ) -> list[tuple[str, str]]:
        return [
            ("Project", portfolio.project_key),
            ("Total releases", format_number(portfolio.release_count)),
            ("Active releases", format_number(portfolio.active_release_count)),
            ("Computed releases", format_number(portfolio.computed_release_count)),
            ("Total sprints", format_number(portfolio.sprint_count)),
            ("Active sprints", format_number(portfolio.active_sprint_count)),
        ]

    def _overview_charts(
        self,
        snapshots: Sequence[MetricSnapshot],
        sprint_snapshots: Sequence[SprintMetricSnapshot],
        sprint_has_story_points: bool = True,
        release_availability: MetricAvailability | None = None,
    ) -> list[ChartSpec]:
        charts = [
            ChartSpec(
                title="Overview Confidence Trend",
                kind="line",
                points=[
                    (
                        format_short_datetime(snapshot.snapshot_at),
                        _release_confidence_for_report(snapshot, release_availability),
                    )
                    for snapshot in snapshots
                ],
                color=self.theme.metric_colors["velocityFit"].rgb,
                y_max=100,
                value_suffix="%",
            ),
            ChartSpec(
                title="Overview Readiness Trend",
                kind="line",
                points=[
                    (
                        format_short_datetime(snapshot.snapshot_at),
                        self.release_template.gate_passed_count(
                            "", snapshot, release_availability
                        ),
                    )
                    for snapshot in snapshots
                ],
                color=self.theme.metric_colors["gatesPassed"].rgb,
            ),
        ]
        if sprint_snapshots and sprint_has_story_points:
            charts.append(
                ChartSpec(
                    title="Overview Sprint Delivery Trend",
                    kind="line",
                    points=[
                        (
                            format_short_datetime(snapshot.snapshot_at),
                            snapshot.delivery_confidence_score,
                        )
                        for snapshot in sprint_snapshots
                    ],
                    color=self.theme.metric_colors["sprintConfidence"].rgb,
                    y_max=100,
                    value_suffix="%",
                )
            )
        return charts
