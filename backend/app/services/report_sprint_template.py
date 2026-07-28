from collections.abc import Sequence
from datetime import datetime

from app.models import SprintMetricSnapshot
from app.services.report_data_preparation import (
    PreparedSnapshotComparison,
    PreparedSprintReportData,
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
    SPRINT_STORY_POINT_UNAVAILABLE_MESSAGE,
    _ruleset_label,
    _sprint_component,
    _sprint_confidence_status_rows,
    _stored_sprint_confidence_artifacts,
    breakdown_rows,
    confidence_band,
    driver_rows,
    format_datetime,
    format_delta,
    format_report_metric_value,
    format_short_datetime,
    recommendation_bullets,
    report_metric_label,
    sprint_quality_rows,
    sprint_risk_bullets,
    sprint_scope_rows,
    sprint_ticket_scope_rows,
    sprint_velocity_rows,
    sprint_work_state_rows,
    sprint_workload_rows,
)


class SprintReportTemplate:
    def __init__(self, theme: PdfTheme | None = None) -> None:
        self.theme = theme or PDFThemeProvider().theme()

    def build_sprint_document(
        self,
        data: PreparedSprintReportData,
        depth: ReportDepth,
        generated_at: datetime,
    ) -> ReportDocument:
        if depth == "summary":
            sections = self._sprint_summary_sections(data)
            title = f"Sprint Summary Report: {data.sprint.name}"
        else:
            sections = self._sprint_sections(data)
            title = f"Sprint Report: {data.sprint.name}"
        return ReportDocument(
            title=title,
            subtitle=f"{data.sprint.project_key} | {data.sprint.sprint_id} | {data.sprint.state}",
            entity_id=data.sprint.sprint_id,
            generated_at=generated_at,
            version=data.version,
            sections=sections,
        )

    def _sprint_sections(
        self,
        data: PreparedSprintReportData,
    ) -> list[ReportSection]:
        sprint = data.sprint
        snapshot = data.snapshot
        snapshots = data.snapshots
        has_story_points = data.has_story_points
        availability = data.availability
        confidence_breakdown, biggest_driver = _stored_sprint_confidence_artifacts(
            snapshot
        )
        delivery_confidence_score = (
            snapshot.delivery_confidence_score
            if snapshot and has_story_points
            else None
        )
        confidence_metric_key = "sprint.delivery_confidence_score"
        blocker_metric_key = "sprint.open_blockers"
        return [
            ReportSection(
                "Executive Summary",
                lines=[
                    "Sprint report generated from deterministic LighthousePM sprint metrics."
                ],
                rows=[
                    ("Sprint", sprint.name),
                    ("Project", sprint.project_key),
                    ("State", sprint.state),
                    ("Start", format_datetime(sprint.start_date)),
                    ("End", format_datetime(sprint.end_date)),
                    (
                        "Latest snapshot",
                        format_datetime(snapshot.snapshot_at if snapshot else None),
                    ),
                    ("Ruleset", _ruleset_label(snapshot)),
                    (
                        report_metric_label(confidence_metric_key),
                        format_report_metric_value(
                            confidence_metric_key, delivery_confidence_score
                        ),
                    ),
                ],
            ),
            ReportSection(
                "Delivery Confidence",
                rows=[
                    *_sprint_confidence_status_rows(snapshot),
                    (
                        "Score",
                        format_report_metric_value(
                            confidence_metric_key, delivery_confidence_score
                        ),
                    ),
                    *sprint_ticket_scope_rows(snapshot, availability),
                    *sprint_work_state_rows(snapshot, availability),
                    (
                        report_metric_label(blocker_metric_key),
                        format_report_metric_value(
                            blocker_metric_key,
                            snapshot.open_blockers if snapshot else None,
                        ),
                    ),
                ],
                charts=[
                    ChartSpec(
                        title="Delivery Confidence Trend",
                        kind="line",
                        points=[
                            (
                                format_short_datetime(item.snapshot_at),
                                item.delivery_confidence_score,
                            )
                            for item in snapshots
                        ],
                        color=self.theme.metric_colors["sprintConfidence"].rgb,
                        y_max=100,
                        value_suffix="%",
                    )
                ]
                if has_story_points
                else [],
            ),
            ReportSection(
                "Confidence Breakdown", rows=breakdown_rows(confidence_breakdown)
            ),
            self._sprint_snapshot_changes(
                sprint.sprint_id,
                snapshots,
                has_story_points,
                data.snapshot_comparison,
            ),
            ReportSection("Biggest Driver", rows=driver_rows(biggest_driver)),
            ReportSection(
                "Velocity Health", rows=sprint_velocity_rows(snapshot, has_story_points)
            ),
            ReportSection("Workload Distribution", rows=sprint_workload_rows(snapshot)),
            ReportSection(
                "Scope Movement", rows=sprint_scope_rows(snapshot, has_story_points)
            ),
            ReportSection(
                "Quality Signals",
                rows=sprint_quality_rows(snapshot, availability),
            ),
            ReportSection(
                "Risk Drivers",
                bullets=sprint_risk_bullets(snapshot, availability),
            ),
            ReportSection(
                "Recommended Actions",
                bullets=recommendation_bullets(data.recommendations),
            ),
            ReportSection(
                "Historical Trends",
                charts=self._sprint_historical_charts(snapshots, has_story_points),
            ),
        ]

    def _sprint_summary_sections(
        self,
        data: PreparedSprintReportData,
    ) -> list[ReportSection]:
        sprint = data.sprint
        snapshot = data.snapshot
        has_story_points = data.has_story_points
        availability = data.availability
        confidence_breakdown, biggest_driver = _stored_sprint_confidence_artifacts(
            snapshot
        )
        delivery_confidence_score = (
            snapshot.delivery_confidence_score
            if snapshot and has_story_points
            else None
        )
        confidence_metric_key = "sprint.delivery_confidence_score"
        return [
            ReportSection(
                "Executive Summary",
                lines=[
                    "Sprint summary generated from deterministic LighthousePM sprint metrics."
                ],
                rows=[
                    ("Sprint", sprint.name),
                    ("Project", sprint.project_key),
                    ("State", sprint.state),
                    ("Start", format_datetime(sprint.start_date)),
                    ("End", format_datetime(sprint.end_date)),
                    (
                        "Latest snapshot",
                        format_datetime(snapshot.snapshot_at if snapshot else None),
                    ),
                    ("Ruleset", _ruleset_label(snapshot)),
                ],
            ),
            ReportSection(
                "Delivery Confidence",
                rows=[
                    *_sprint_confidence_status_rows(snapshot),
                    (
                        "Score",
                        format_report_metric_value(
                            confidence_metric_key, delivery_confidence_score
                        ),
                    ),
                    ("Band", confidence_band(delivery_confidence_score)),
                    *sprint_ticket_scope_rows(snapshot, availability),
                    *sprint_work_state_rows(snapshot, availability),
                ],
            ),
            ReportSection(
                "Confidence Breakdown", rows=breakdown_rows(confidence_breakdown)
            ),
            ReportSection("Biggest Driver", rows=driver_rows(biggest_driver)),
            ReportSection("Workload Distribution", rows=sprint_workload_rows(snapshot)),
            ReportSection(
                "Top Risks",
                bullets=sprint_risk_bullets(snapshot, availability)[:3],
            ),
            ReportSection(
                "Top Recommendations",
                bullets=recommendation_bullets(data.recommendations, limit=3),
            ),
        ]

    def _sprint_snapshot_changes(
        self,
        sprint_id: str,
        snapshots: tuple[SprintMetricSnapshot, ...],
        has_story_points: bool = True,
        comparison: PreparedSnapshotComparison | None = None,
    ) -> ReportSection:
        if not has_story_points:
            return ReportSection(
                "Snapshot Changes", lines=[SPRINT_STORY_POINT_UNAVAILABLE_MESSAGE]
            )
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
                (
                    "Confidence delta",
                    format_delta(comparison.confidence_delta)
                    if comparison.confidence_delta is not None
                    else "N/A",
                ),
                ("Primary driver", comparison.primary_driver),
                ("Entity", sprint_id),
            ],
        )

    def _sprint_historical_charts(
        self,
        snapshots: Sequence[SprintMetricSnapshot],
        has_story_points: bool = True,
    ) -> list[ChartSpec]:
        story_point_charts = (
            [
                ChartSpec(
                    title="Historical Delivery Confidence",
                    kind="line",
                    points=[
                        (
                            format_short_datetime(snapshot.snapshot_at),
                            snapshot.delivery_confidence_score,
                        )
                        for snapshot in snapshots
                    ],
                    color=self.theme.metric_colors["sprintConfidence"].rgb,
                    y_max=100,
                    value_suffix="%",
                ),
                ChartSpec(
                    title="Historical Progress Alignment",
                    kind="line",
                    points=[
                        (
                            format_short_datetime(snapshot.snapshot_at),
                            _sprint_component(snapshot, "progress_alignment"),
                        )
                        for snapshot in snapshots
                    ],
                    color=self.theme.metric_colors["progressAlignment"].rgb,
                    y_max=100,
                    value_suffix="%",
                ),
                ChartSpec(
                    title="Historical Velocity Fit",
                    kind="line",
                    points=[
                        (
                            format_short_datetime(snapshot.snapshot_at),
                            _sprint_component(snapshot, "velocity_fit"),
                        )
                        for snapshot in snapshots
                    ],
                    color=self.theme.metric_colors["velocityFit"].rgb,
                    y_max=100,
                    value_suffix="%",
                ),
                ChartSpec(
                    title="Historical Scope Stability",
                    kind="line",
                    points=[
                        (
                            format_short_datetime(snapshot.snapshot_at),
                            _sprint_component(snapshot, "scope_stability"),
                        )
                        for snapshot in snapshots
                    ],
                    color=self.theme.metric_colors["scopeStability"].rgb,
                    y_max=100,
                    value_suffix="%",
                ),
                ChartSpec(
                    title="Historical Blocker Health",
                    kind="line",
                    points=[
                        (
                            format_short_datetime(snapshot.snapshot_at),
                            _sprint_component(snapshot, "blocker_penalty"),
                        )
                        for snapshot in snapshots
                    ],
                    color=self.theme.metric_colors["blockerHealth"].rgb,
                    y_max=100,
                    value_suffix="%",
                ),
            ]
            if has_story_points
            else []
        )
        ticket_count_charts = [
            ChartSpec(
                title="Historical Scope Completion",
                kind="line",
                points=[
                    (
                        format_short_datetime(snapshot.snapshot_at),
                        snapshot.completed_scope_pct,
                    )
                    for snapshot in snapshots
                ],
                color=self.theme.metric_colors["scopeCompleted"].rgb,
                y_max=100,
                value_suffix="%",
            ),
            ChartSpec(
                title="Historical Scope Creep",
                kind="line",
                points=[
                    (
                        format_short_datetime(snapshot.snapshot_at),
                        snapshot.scope_creep_pct,
                    )
                    for snapshot in snapshots
                ],
                color=self.theme.metric_colors["scopeChurn"].rgb,
                value_suffix="%",
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
                title="Historical Bugs Created During Sprint",
                kind="bar",
                points=[
                    (
                        format_short_datetime(snapshot.snapshot_at),
                        snapshot.bugs_created_during_sprint,
                    )
                    for snapshot in snapshots
                ],
                color=self.theme.metric_colors["confidenceWatch"].rgb,
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
        return [*story_point_charts, *ticket_count_charts]
