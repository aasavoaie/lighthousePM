from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from importlib import metadata
from pathlib import Path
import sys
import tomllib
from typing import Literal
import zlib

from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import MetricSnapshot, Release, Sprint, SprintMetricSnapshot
from app.repositories.metric_repository import MetricRepository
from app.repositories.release_repository import ReleaseRepository
from app.repositories.signal_repository import SignalRepository
from app.repositories.sprint_repository import SprintRepository
from app.services.confidence_breakdown_service import ConfidenceBreakdownService
from app.services.driver_analysis_service import DriverAnalysisService
from app.services.jira_field_mapper import JiraFieldMapper
from app.services.metric_availability_service import MetricAvailabilityService
from app.schemas.availability import MetricAvailability
from app.schemas.confidence import ConfidenceBreakdown
from app.schemas.drivers import DriverAnalysis
from app.services.recommendation_engine import RecommendationEngine
from app.services.signal_service import SignalService
from app.services.snapshot_comparison_service import SnapshotComparisonService


ReportDepth = Literal["summary", "full"]
SPRINT_STORY_POINT_UNAVAILABLE_MESSAGE = (
    "Delivery confidence requires at least 50% of sprint tickets to have valid story points."
)
RELEASE_NO_TICKETS_MESSAGE = "No tickets are available for this scope."
RELEASE_NO_STORY_POINTS_MESSAGE = "No tickets in this scope have story points."


def _release_metric_availability(session: Session, release_id: str):
    return MetricAvailabilityService.build_release_availability(
        session=session,
        release_id=release_id,
        field_mapper=JiraFieldMapper(get_settings()),
    )


@dataclass(frozen=True)
class PdfColor:
    hex: str
    rgb: tuple[float, float, float]


@dataclass(frozen=True)
class PdfTypography:
    body_font: str
    heading_font: str
    title_size: int
    section_size: int
    body_size: int
    small_size: int


@dataclass(frozen=True)
class PdfSpacing:
    page_margin: int
    footer_height: int
    section_gap: int
    row_padding: int
    chart_height: int


@dataclass(frozen=True)
class PdfTableStyle:
    label_width: int
    background: PdfColor
    border: PdfColor
    label: PdfColor


@dataclass(frozen=True)
class PdfSectionStyle:
    heading: PdfColor
    body: PdfColor
    muted: PdfColor
    accent: PdfColor


@dataclass(frozen=True)
class PdfTheme:
    palette: dict[str, PdfColor]
    status_colors: dict[str, PdfColor]
    confidence_colors: dict[str, PdfColor]
    metric_colors: dict[str, PdfColor]
    typography: PdfTypography
    spacing: PdfSpacing
    section: PdfSectionStyle
    table: PdfTableStyle


class PDFThemeProvider:
    """Provides the LighthousePM PDF palette and layout tokens."""

    def theme(self) -> PdfTheme:
        palette = {
            "text": pdf_color("#122033"),
            "muted": pdf_color("#58677c"),
            "label": pdf_color("#304a68"),
            "border": pdf_color("#d6e0ea"),
            "table_background": pdf_color("#f6f9fc"),
            "page": pdf_color("#ffffff"),
            "primary": pdf_color("#0b6bcb"),
            "green": pdf_color("#237445"),
            "amber": pdf_color("#e48f00"),
            "risk_amber": pdf_color("#9f6a00"),
            "red": pdf_color("#c43c2d"),
            "purple": pdf_color("#6f42c1"),
        }
        return PdfTheme(
            palette=palette,
            status_colors={
                "GREEN": palette["green"],
                "YELLOW": palette["amber"],
                "RED": palette["red"],
                "good": palette["green"],
                "warning": palette["amber"],
                "critical": palette["red"],
            },
            confidence_colors={
                "high": palette["green"],
                "medium": palette["amber"],
                "low": palette["red"],
            },
            metric_colors={
                "blockers": palette["red"],
                "bugs": palette["amber"],
                "scopeCompleted": palette["primary"],
                "completedTickets": palette["green"],
                "scopeChurn": palette["purple"],
                "cycleTime": palette["green"],
                "reopenRate": palette["risk_amber"],
                "sprintConfidence": palette["green"],
                "confidenceWatch": palette["amber"],
                "confidenceRisk": palette["risk_amber"],
                "confidenceCritical": palette["red"],
                "progressAlignment": palette["primary"],
                "velocityFit": palette["purple"],
                "blockerHealth": palette["green"],
                "scopeStability": palette["risk_amber"],
                "readiness": palette["primary"],
                "gatesPassed": palette["green"],
                "neutralRisk": pdf_color("#58677c"),
                "committedScope": palette["primary"],
                "completedScope": palette["green"],
                "releasedStoryPoints": palette["primary"],
                "unreleasedStoryPoints": palette["amber"],
                "closedSprintStoryPoints": palette["primary"],
                "notClosedSprintStoryPoints": palette["amber"],
            },
            typography=PdfTypography(
                body_font="F1",
                heading_font="F2",
                title_size=20,
                section_size=14,
                body_size=10,
                small_size=8,
            ),
            spacing=PdfSpacing(
                page_margin=48,
                footer_height=32,
                section_gap=8,
                row_padding=8,
                chart_height=150,
            ),
            section=PdfSectionStyle(
                heading=palette["text"],
                body=palette["text"],
                muted=palette["muted"],
                accent=palette["primary"],
            ),
            table=PdfTableStyle(
                label_width=170,
                background=palette["table_background"],
                border=palette["border"],
                label=palette["label"],
            ),
        )

    def confidence_color(self, confidence_score: float | None) -> PdfColor:
        theme = self.theme()
        if confidence_score is None:
            return theme.palette["muted"]
        if confidence_score >= 91:
            return theme.confidence_colors["high"]
        if confidence_score >= 61:
            return theme.confidence_colors["medium"]
        return theme.confidence_colors["low"]


@dataclass(frozen=True)
class ChartSpec:
    title: str
    kind: Literal["line", "bar"]
    points: list[tuple[str, float | None]]
    color: tuple[float, float, float] = field(default_factory=lambda: pdf_color("#0b6bcb").rgb)
    y_max: float | None = None
    value_suffix: str = ""


@dataclass(frozen=True)
class ChartImage:
    width: int
    height: int
    rgb_data: bytes


class ChartExportService:
    """Render report chart specs into high-resolution RGB images."""

    def __init__(self, theme: PdfTheme | None = None, scale: int = 3) -> None:
        self.theme = theme or PDFThemeProvider().theme()
        self.scale = scale

    def export_chart_image(self, chart: ChartSpec, width: int = 516, height: int = 150) -> ChartImage:
        image_width = width * self.scale
        image_height = height * self.scale
        canvas = _RasterCanvas(
            width=image_width,
            height=image_height,
            background=_rgb255(self.theme.palette["page"].rgb),
        )
        values = [(label, value) for label, value in chart.points if value is not None]
        border = _rgb255(self.theme.table.border.rgb)
        muted = _rgb255(self.theme.section.muted.rgb)
        chart_color = _rgb255(chart.color)
        canvas.rect(0, 0, image_width - 1, image_height - 1, outline=border)
        if not values:
            canvas.line(28 * self.scale, image_height // 2, image_width - 28 * self.scale, image_height // 2, muted)
            return ChartImage(width=image_width, height=image_height, rgb_data=canvas.bytes())

        numeric_values = [float(value) for _, value in values]
        max_value = max(chart.y_max or max(max(numeric_values), 1.0), 1.0)
        plot_left = 42 * self.scale
        plot_right = image_width - 24 * self.scale
        plot_bottom = image_height - 28 * self.scale
        plot_top = 20 * self.scale
        mid_y = plot_top + (plot_bottom - plot_top) // 2
        canvas.line(plot_left, plot_top, plot_right, plot_top, border)
        canvas.line(plot_left, mid_y, plot_right, mid_y, border)
        canvas.line(plot_left, plot_bottom, plot_right, plot_bottom, border)
        canvas.line(plot_left, plot_top, plot_left, plot_bottom, border)

        if chart.kind == "bar":
            self._render_bar_chart(canvas, values, max_value, plot_left, plot_right, plot_top, plot_bottom, chart_color)
        else:
            self._render_line_chart(canvas, values, max_value, plot_left, plot_right, plot_top, plot_bottom, chart_color)
        return ChartImage(width=image_width, height=image_height, rgb_data=canvas.bytes())

    def _render_line_chart(
        self,
        canvas: "_RasterCanvas",
        values: list[tuple[str, float]],
        max_value: float,
        plot_left: int,
        plot_right: int,
        plot_top: int,
        plot_bottom: int,
        color: tuple[int, int, int],
    ) -> None:
        if len(values) == 1:
            x = plot_right
            y = _chart_y(float(values[0][1]), max_value, plot_top, plot_bottom)
            canvas.circle(x, y, max(2, self.scale * 2), color)
            return

        points: list[tuple[int, int]] = []
        plot_width = plot_right - plot_left
        for index, (_, value) in enumerate(values):
            x = plot_left + round((index / (len(values) - 1)) * plot_width)
            y = _chart_y(float(value), max_value, plot_top, plot_bottom)
            points.append((x, y))

        stroke_width = max(2, self.scale * 2)
        for left, right in zip(points, points[1:]):
            canvas.line(left[0], left[1], right[0], right[1], color, width=stroke_width)
        for x, y in points:
            canvas.circle(x, y, max(2, self.scale * 2), color)

    def _render_bar_chart(
        self,
        canvas: "_RasterCanvas",
        values: list[tuple[str, float]],
        max_value: float,
        plot_left: int,
        plot_right: int,
        plot_top: int,
        plot_bottom: int,
        color: tuple[int, int, int],
    ) -> None:
        gap = max(4, 6 * self.scale)
        plot_width = plot_right - plot_left
        bar_width = max(6, (plot_width - gap * (len(values) - 1)) // len(values))
        for index, (_, value) in enumerate(values):
            height = round((float(value) / max_value) * (plot_bottom - plot_top))
            x = plot_left + index * (bar_width + gap)
            canvas.fill_rect(x, plot_bottom - height, min(bar_width, plot_right - x), height, color)


@dataclass(frozen=True)
class ReportSection:
    title: str
    lines: list[str] = field(default_factory=list)
    rows: list[tuple[str, str]] = field(default_factory=list)
    bullets: list[str] = field(default_factory=list)
    charts: list[ChartSpec] = field(default_factory=list)
    heading_color: tuple[float, float, float] | None = None


@dataclass(frozen=True)
class ReportDocument:
    title: str
    subtitle: str
    entity_id: str
    generated_at: datetime
    version: str
    sections: list[ReportSection]


class SimplePdfRenderer:
    """Small deterministic PDF renderer for text, metric tables, and simple charts."""

    page_width = 612
    page_height = 792

    def __init__(
        self,
        generated_at: datetime,
        version: str,
        theme: PdfTheme | None = None,
        chart_export_service: ChartExportService | None = None,
    ) -> None:
        self.generated_at = generated_at
        self.version = version
        self.theme = theme or PDFThemeProvider().theme()
        self.chart_export_service = chart_export_service or ChartExportService(theme=self.theme)
        self.margin = self.theme.spacing.page_margin
        self.footer_height = self.theme.spacing.footer_height
        self._pages: list[list[str]] = []
        self._content: list[str] = []
        self._y = self.page_height - self.margin
        self._section_index = 0
        self._new_page()

    def render(self, document: ReportDocument) -> bytes:
        self.report_header(document)
        for section in document.sections:
            self.section(section)
        self._finish_page()
        return _build_pdf(self._pages)

    def report_header(self, document: ReportDocument) -> None:
        self._ensure_space(110)
        app_row_center_y = self._y - 10
        self._logo(self.margin, app_row_center_y)
        self._text(
            self.margin + 34,
            app_row_center_y - 4,
            "LighthousePM",
            size=12,
            font=self.theme.typography.heading_font,
            color=self.theme.section.heading.rgb,
        )
        self._y = app_row_center_y - 42
        self.heading(document.title, size=self.theme.typography.title_size)
        self.text(document.subtitle, size=self.theme.typography.body_size, color=self.theme.section.muted.rgb)
        self.text(
            f"Generated {format_datetime(document.generated_at)} | Version {document.version}",
            size=self.theme.typography.small_size + 1,
            color=self.theme.section.muted.rgb,
        )
        self.spacer(14)

    def section(self, section: ReportSection) -> None:
        self._ensure_space(78)
        if self._section_index > 0:
            self._section_divider()
        self._section_index += 1
        self.heading(section.title, size=self.theme.typography.section_size, color=section.heading_color)
        for line in section.lines:
            self.wrapped_text(line)
        if section.rows:
            self.rows(section.rows)
        for bullet in section.bullets:
            self.bullet(bullet)
        for chart in section.charts:
            self.chart(chart)
        self.spacer(self.theme.spacing.section_gap + 12)

    def heading(self, value: str, size: int, color: tuple[float, float, float] | None = None) -> None:
        self._ensure_space(size + 10)
        self._text(
            self.margin,
            self._y,
            value,
            size=size,
            font=self.theme.typography.heading_font,
            color=color or self.theme.section.heading.rgb,
        )
        self._y -= size + 7

    def text(self, value: str, size: int = 10, color: tuple[float, float, float] | None = None) -> None:
        self._ensure_space(size + 6)
        self._text(self.margin, self._y, value, size=size, color=color or self.theme.section.body.rgb)
        self._y -= size + 5

    def wrapped_text(self, value: str, size: int = 10) -> None:
        for line in _wrap(value, 96):
            self.text(line, size=size)

    def bullet(self, value: str) -> None:
        for index, line in enumerate(_wrap(value, 88)):
            self._ensure_space(15)
            prefix = "- " if index == 0 else "  "
            self._text(self.margin + 8, self._y, f"{prefix}{line}", size=10)
            self._y -= 15

    def rows(self, rows: list[tuple[str, str]]) -> None:
        key_width = self.theme.table.label_width
        value_x = self.margin + key_width + 10
        for label, value in rows:
            value_lines = _wrap(value, 62)
            row_height = max(18, len(value_lines) * 13 + 4)
            self._ensure_space(row_height)
            self._rect(
                self.margin,
                self._y - row_height + 6,
                self.page_width - 2 * self.margin,
                row_height,
                fill=self.theme.table.background.rgb,
                stroke=self.theme.table.border.rgb,
            )
            self._text(
                self.margin + self.theme.spacing.row_padding,
                self._y - 8,
                label,
                size=9,
                font=self.theme.typography.heading_font,
                color=self.theme.table.label.rgb,
            )
            line_y = self._y - 8
            for value_line in value_lines:
                self._text(value_x, line_y, value_line, size=9, color=self.theme.section.body.rgb)
                line_y -= 13
            self._y -= row_height + 3

    def chart(self, chart: ChartSpec) -> None:
        chart_height = self.theme.spacing.chart_height
        self._ensure_space(chart_height + 50)
        self._text(self.margin, self._y, chart.title, size=10, font=self.theme.typography.heading_font)
        self._y -= 16
        x = self.margin
        y = self._y - chart_height
        width = self.page_width - 2 * self.margin
        image = self.chart_export_service.export_chart_image(chart, width=int(width), height=chart_height)
        self._image(x, y, width, chart_height, image)
        values = [(label, value) for label, value in chart.points if value is not None]
        if not values:
            self._text(x + 16, y + chart_height / 2, "No chart data available.", size=10, color=self.theme.section.muted.rgb)
        else:
            self._chart_scale_labels(chart, values, x, y, width, chart_height)
        self._y = y - 28

    def _chart_scale_labels(
        self,
        chart: ChartSpec,
        values: list[tuple[str, float]],
        x: float,
        y: float,
        width: float,
        height: float,
    ) -> None:
        max_value = _chart_max_value(chart, values)
        mid_value = max_value / 2
        plot_left = x + 42
        plot_right = x + width - 24
        plot_bottom = y + 28
        plot_top = y + height - 20
        plot_mid = plot_top - (plot_top - plot_bottom) / 2

        labels = [
            (max_value, plot_top - 3),
            (mid_value, plot_mid - 3),
            (0.0, plot_bottom - 3),
        ]
        for value, label_y in labels:
            self._text(x + 4, label_y, _format_scale_value(value, chart.value_suffix), size=7, color=self.theme.section.muted.rgb)

        first_label = values[0][0]
        middle_label = values[len(values) // 2][0]
        last_label = values[-1][0]
        self._text(plot_left, y + 10, first_label[:18], size=7, color=self.theme.section.muted.rgb)
        if len(values) > 2:
            self._text((plot_left + plot_right) / 2 - 28, y + 10, middle_label[:18], size=7, color=self.theme.section.muted.rgb)
        self._text(plot_right - 70, y + 10, last_label[:18], size=7, color=self.theme.section.muted.rgb)

        scale_text = (
            f"Scale: 0{chart.value_suffix} / "
            f"{_format_scale_value(mid_value, chart.value_suffix)} / "
            f"{_format_scale_value(max_value, chart.value_suffix)}"
        )
        self._text(plot_left, y - 12, scale_text, size=7, color=self.theme.section.muted.rgb)

    def spacer(self, amount: int) -> None:
        self._y -= amount

    def _section_divider(self) -> None:
        self._ensure_space(24)
        self._line(
            self.margin,
            self._y,
            self.page_width - self.margin,
            self._y,
            stroke=self.theme.table.border.rgb,
        )
        self._y -= 18

    def _line_chart(
        self,
        values: list[tuple[str, float]],
        x: float,
        y: float,
        width: float,
        height: float,
        max_value: float,
        color: tuple[float, float, float],
    ) -> None:
        if len(values) == 1:
            px = x + width
            py = y + (values[0][1] / max_value) * height
            self._circle(px, py, 2.5, fill=color)
            return
        points: list[tuple[float, float]] = []
        for index, (_, value) in enumerate(values):
            px = x + (index / (len(values) - 1)) * width
            py = y + (float(value) / max_value) * height
            points.append((px, py))
        self._polyline(points, stroke=color)
        for px, py in points:
            self._circle(px, py, 1.8, fill=color)

    def _bar_chart(
        self,
        values: list[tuple[str, float]],
        x: float,
        y: float,
        width: float,
        height: float,
        max_value: float,
        color: tuple[float, float, float],
    ) -> None:
        bar_gap = 6
        bar_width = max(8, (width - bar_gap * (len(values) - 1)) / len(values))
        for index, (_, value) in enumerate(values):
            bar_height = (float(value) / max_value) * height
            bx = x + index * (bar_width + bar_gap)
            self._rect(bx, y, bar_width, bar_height, fill=color, stroke=color)

    def _ensure_space(self, needed: int) -> None:
        if self._y - needed < self.margin + self.footer_height:
            self._finish_page()
            self._new_page()

    def _new_page(self) -> None:
        self._content = []
        self._y = self.page_height - self.margin

    def _finish_page(self) -> None:
        page_number = len(self._pages) + 1
        footer = (
            f"Generated by LighthousePM | Page {page_number} | "
            f"{format_datetime(self.generated_at)} | Version {self.version}"
        )
        self._text(self.margin, 28, footer, size=self.theme.typography.small_size, color=self.theme.section.muted.rgb)
        self._pages.append(self._content)

    def _text(
        self,
        x: float,
        y: float,
        value: str,
        size: int = 10,
        font: Literal["F1", "F2"] = "F1",
        color: tuple[float, float, float] | None = None,
    ) -> None:
        color = color or self.theme.section.body.rgb
        self._content.append(f"{_pdf_rgb(color)} rg")
        self._content.append(f"BT /{font} {size} Tf {x:.2f} {y:.2f} Td ({_pdf_escape(value)}) Tj ET")

    def _rect(
        self,
        x: float,
        y: float,
        width: float,
        height: float,
        fill: tuple[float, float, float],
        stroke: tuple[float, float, float],
    ) -> None:
        self._content.append(f"{_pdf_rgb(fill)} rg {_pdf_rgb(stroke)} RG")
        self._content.append(f"{x:.2f} {y:.2f} {width:.2f} {height:.2f} re B")

    def _line(self, x1: float, y1: float, x2: float, y2: float, stroke: tuple[float, float, float]) -> None:
        self._content.append(f"{_pdf_rgb(stroke)} RG 1 w {x1:.2f} {y1:.2f} m {x2:.2f} {y2:.2f} l S")

    def _polyline(self, points: list[tuple[float, float]], stroke: tuple[float, float, float]) -> None:
        if not points:
            return
        operations = [f"{_pdf_rgb(stroke)} RG 2 w {points[0][0]:.2f} {points[0][1]:.2f} m"]
        operations.extend(f"{x:.2f} {y:.2f} l" for x, y in points[1:])
        operations.append("S")
        self._content.append(" ".join(operations))

    def _circle(self, x: float, y: float, radius: float, fill: tuple[float, float, float]) -> None:
        self._content.append(f"{_pdf_rgb(fill)} rg")
        self._content.append(f"{x - radius:.2f} {y - radius:.2f} {radius * 2:.2f} {radius * 2:.2f} re f")

    def _image(self, x: float, y: float, width: float, height: float, image: ChartImage) -> None:
        compressed_hex = zlib.compress(image.rgb_data).hex()
        self._content.append(
            f"q {width:.2f} 0 0 {height:.2f} {x:.2f} {y:.2f} cm "
            f"BI /W {image.width} /H {image.height} /CS /RGB /BPC 8 /F [/AHx /Fl] "
            f"ID {compressed_hex}> EI Q"
        )

    def _logo(self, x: float, y: float) -> None:
        primary = self.theme.palette["primary"].rgb
        green = self.theme.metric_colors["sprintConfidence"].rgb
        self._rect(x, y - 11, 22, 22, fill=self.theme.palette["page"].rgb, stroke=primary)
        self._line(x + 5, y - 6, x + 11, y + 5, stroke=primary)
        self._line(x + 11, y + 5, x + 17, y - 6, stroke=green)
        self._circle(x + 11, y + 5, 2, fill=green)


class ReportTemplateEngine:
    """Build reusable release and sprint report documents."""

    def __init__(self, theme: PdfTheme | None = None) -> None:
        self.theme = theme or PDFThemeProvider().theme()

    def build_release_document(
        self,
        session: Session,
        release: Release,
        depth: ReportDepth,
        generated_at: datetime,
    ) -> ReportDocument:
        snapshot = MetricRepository.get_latest_snapshot(session=session, release_id=release.release_id)
        snapshots = MetricRepository.list_snapshots_for_release(session=session, release_id=release.release_id, limit=30)
        if depth == "summary":
            sections = self._release_summary_sections(session, release, snapshot)
            title = f"Release Summary Report: {release.name}"
        else:
            sections = self._release_sections(session, release, snapshot, snapshots)
            title = f"Release Report: {release.name}"
        return ReportDocument(
            title=title,
            subtitle=f"{release.project_key} | {release.release_id} | {release.status or 'Unknown status'}",
            entity_id=release.release_id,
            generated_at=generated_at,
            version=application_version(),
            sections=sections,
        )

    def build_sprint_document(
        self,
        session: Session,
        sprint: Sprint,
        depth: ReportDepth,
        generated_at: datetime,
    ) -> ReportDocument:
        snapshot = SprintRepository.get_latest_metric_snapshot(session=session, sprint_id=sprint.sprint_id)
        snapshots = SprintRepository.list_metric_snapshots_for_sprint(session=session, sprint_id=sprint.sprint_id, limit=30)
        if depth == "summary":
            sections = self._sprint_summary_sections(session, sprint, snapshot)
            title = f"Sprint Summary Report: {sprint.name}"
        else:
            sections = self._sprint_sections(session, sprint, snapshot, snapshots)
            title = f"Sprint Report: {sprint.name}"
        return ReportDocument(
            title=title,
            subtitle=f"{sprint.project_key} | {sprint.sprint_id} | {sprint.state}",
            entity_id=sprint.sprint_id,
            generated_at=generated_at,
            version=application_version(),
            sections=sections,
        )

    def build_overview_document(
        self,
        session: Session,
        release: Release,
        generated_at: datetime,
    ) -> ReportDocument:
        snapshot = MetricRepository.get_latest_snapshot(session=session, release_id=release.release_id)
        snapshots = MetricRepository.list_snapshots_for_release(session=session, release_id=release.release_id, limit=30)
        sprint = SprintRepository.get_current_sprint(session=session, project_key=release.project_key)
        sprint_snapshot = (
            SprintRepository.get_latest_metric_snapshot(session=session, sprint_id=sprint.sprint_id) if sprint else None
        )
        sprint_snapshots = (
            SprintRepository.list_metric_snapshots_for_sprint(session=session, sprint_id=sprint.sprint_id, limit=30)
            if sprint
            else []
        )
        return ReportDocument(
            title=f"Overview Dashboard Report: {release.name}",
            subtitle=f"{release.project_key} | {release.release_id} | {release.status or 'Unknown status'}",
            entity_id=release.release_id,
            generated_at=generated_at,
            version=application_version(),
            sections=self._overview_sections(
                session=session,
                release=release,
                snapshot=snapshot,
                snapshots=snapshots,
                sprint=sprint,
                sprint_snapshot=sprint_snapshot,
                sprint_snapshots=sprint_snapshots,
            ),
        )

    def build_documentation_document(self, generated_at: datetime) -> ReportDocument:
        title, sections = _documentation_sections_from_markdown(_read_about_documentation())
        return ReportDocument(
            title=title,
            subtitle="Product documentation for Overview, Releases, and Sprints",
            entity_id="documentation",
            generated_at=generated_at,
            version=application_version(),
            sections=sections,
        )

    def _overview_sections(
        self,
        session: Session,
        release: Release,
        snapshot: MetricSnapshot | None,
        snapshots: list[MetricSnapshot],
        sprint: Sprint | None,
        sprint_snapshot: SprintMetricSnapshot | None,
        sprint_snapshots: list[SprintMetricSnapshot],
    ) -> list[ReportSection]:
        readiness = self._release_readiness(session, release.release_id, snapshot)
        release_availability = _release_metric_availability(session, release.release_id)
        recommendations = (
            RecommendationEngine.build_release_recommendations(
                snapshot,
                metric_availability=release_availability,
            )
            if snapshot
            else []
        )
        sprint_issues = SprintRepository.list_all_sprint_issues(session=session, sprint_id=sprint.sprint_id) if sprint else []
        sprint_has_story_points = _sprint_confidence_available(sprint_snapshot)
        sprint_recommendations = (
            RecommendationEngine.build_sprint_recommendations(
                sprint_snapshot,
                sprint_issues=sprint_issues,
                include_story_point_rules=sprint_has_story_points,
            )
            if sprint_snapshot
            else []
        )
        sprint_delivery_confidence = (
            sprint_snapshot.delivery_confidence_score
            if sprint_snapshot and sprint_has_story_points
            else None
        )
        confidence_score = readiness.get("confidence_score")
        confidence_delta = _first_last_delta(
            [_release_confidence_for_report(item, release_availability) for item in snapshots]
        )
        outlook_section = self._release_outlook_section(session, release, snapshot, readiness)
        risk_aging_section = self._release_risk_aging_section(session, release, snapshot)
        return [
            ReportSection(
                "Executive Summary",
                lines=[readiness.get("summary") or "Overview dashboard exported from deterministic LighthousePM data."],
                rows=[
                    ("Release", release.name),
                    ("Project", release.project_key),
                    ("Release status", release.status or "Unknown"),
                    ("Release date", format_datetime(release.release_date)),
                    ("Current sprint", sprint.name if sprint else "No active sprint"),
                    ("Latest release snapshot", _overview_release_snapshot_label(snapshot)),
                    ("Release ruleset", _ruleset_label(snapshot)),
                    ("Latest sprint snapshot", _overview_sprint_snapshot_label(sprint, sprint_snapshot)),
                    ("Sprint ruleset", _ruleset_label(sprint_snapshot)),
                ],
            ),
            outlook_section,
            risk_aging_section,
            ReportSection("Project Portfolio Metrics", rows=self._portfolio_metric_rows(session, release.project_key)),
            ReportSection("Release Metrics", rows=release_metric_rows(snapshot, release_availability)),
            ReportSection(
                "Sprint Metrics",
                rows=overview_sprint_metric_rows(sprint, sprint_snapshot, sprint_has_story_points),
            ),
            ReportSection(
                "Confidence Metrics",
                rows=[
                    ("Release confidence", format_percent(confidence_score)),
                    ("Release confidence band", confidence_band(confidence_score)),
                    ("Confidence delta", format_delta(confidence_delta) if confidence_delta is not None else "N/A"),
                    ("Readiness", format_percent(readiness.get("readiness_pct"))),
                    (
                        "Sprint delivery confidence",
                        format_percent(sprint_delivery_confidence),
                    ),
                    (
                        "Sprint confidence band",
                        confidence_band(sprint_delivery_confidence),
                    ),
                ],
            ),
            ReportSection("Risk Indicators", bullets=overview_risk_bullets(readiness, snapshot, sprint_snapshot)),
            ReportSection("Signals", rows=overview_signal_rows(readiness)),
            ReportSection(
                "Trends",
                charts=self._overview_charts(snapshots, sprint_snapshots, sprint_has_story_points, release_availability),
            ),
            ReportSection(
                "Health Indicators",
                rows=overview_health_rows(readiness, snapshot, sprint_snapshot, sprint_has_story_points),
            ),
            ReportSection(
                "Recommendations",
                bullets=overview_recommendation_bullets(recommendations, sprint_recommendations),
            ),
        ]

    def _portfolio_metric_rows(self, session: Session, project_key: str) -> list[tuple[str, str]]:
        releases, release_count = ReleaseRepository.list_releases(
            session=session,
            project_key=project_key,
            skip=0,
            limit=1000,
        )
        sprints, sprint_count = SprintRepository.list_sprints(
            session=session,
            project_key=project_key,
            skip=0,
            limit=1000,
        )
        active_releases = sum(1 for item in releases if (item.status or "").casefold() in {"active", "unreleased"})
        active_sprints = sum(1 for item in sprints if item.state.casefold() == "active")
        computed_releases = sum(
            1
            for item in releases
            if MetricRepository.get_latest_snapshot(session=session, release_id=item.release_id) is not None
        )
        return [
            ("Project", project_key),
            ("Total releases", format_number(release_count)),
            ("Active releases", format_number(active_releases)),
            ("Computed releases", format_number(computed_releases)),
            ("Total sprints", format_number(sprint_count)),
            ("Active sprints", format_number(active_sprints)),
        ]

    def _overview_charts(
        self,
        snapshots: list[MetricSnapshot],
        sprint_snapshots: list[SprintMetricSnapshot],
        sprint_has_story_points: bool = True,
        release_availability: MetricAvailability | None = None,
    ) -> list[ChartSpec]:
        charts = [
            ChartSpec(
                title="Overview Confidence Trend",
                kind="line",
                points=[
                    (format_short_datetime(snapshot.snapshot_at), _release_confidence_for_report(snapshot, release_availability))
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
                    (format_short_datetime(snapshot.snapshot_at), self._release_gate_passed_count("", snapshot, release_availability))
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
                        (format_short_datetime(snapshot.snapshot_at), snapshot.delivery_confidence_score)
                        for snapshot in sprint_snapshots
                    ],
                    color=self.theme.metric_colors["sprintConfidence"].rgb,
                    y_max=100,
                    value_suffix="%",
                )
            )
        return charts

    def _release_sections(
        self,
        session: Session,
        release: Release,
        snapshot: MetricSnapshot | None,
        snapshots: list[MetricSnapshot],
    ) -> list[ReportSection]:
        readiness = self._release_readiness(session, release.release_id, snapshot)
        confidence_breakdown, biggest_driver = _stored_release_confidence_artifacts(snapshot)
        release_availability = _release_metric_availability(session, release.release_id)
        if not release_availability.context.has_tickets:
            confidence_breakdown = None
            biggest_driver = None
        recommendations = (
            RecommendationEngine.build_release_recommendations(
                snapshot,
                metric_availability=release_availability,
            )
            if snapshot
            else []
        )
        outlook_section = self._release_outlook_section(session, release, snapshot, readiness)
        risk_aging_section = self._release_risk_aging_section(session, release, snapshot)
        return [
            ReportSection(
                "Executive Summary",
                lines=[readiness.get("summary") or "Release report generated from deterministic LighthousePM snapshots."],
                rows=[
                    ("Release", release.name),
                    ("Project", release.project_key),
                    ("Status", release.status or "Unknown"),
                    ("Release date", format_datetime(release.release_date)),
                    ("Latest snapshot", format_datetime(snapshot.snapshot_at if snapshot else None)),
                    ("Ruleset", _ruleset_label(snapshot)),
                    ("Signal", str(readiness.get("status_label") or readiness.get("signal") or "Not computed")),
                    ("Confidence", format_percent(readiness.get("confidence_score"))),
                ],
            ),
            outlook_section,
            risk_aging_section,
            ReportSection("Confidence Breakdown", rows=breakdown_rows(confidence_breakdown)),
            ReportSection(
                "Confidence Trend",
                charts=[
                    ChartSpec(
                        title="Confidence Score",
                        kind="line",
                        points=[
                            (format_short_datetime(item.snapshot_at), _release_confidence_for_report(item, release_availability))
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
                                self._release_readiness(session, release.release_id, item).get("readiness_pct"),
                            )
                            for item in snapshots
                        ],
                        color=self.theme.metric_colors["readiness"].rgb,
                        y_max=100,
                        value_suffix="%",
                    ),
                ],
            ),
            self._release_snapshot_changes(release.release_id, snapshots),
            ReportSection("Biggest Driver", rows=driver_rows(biggest_driver)),
            ReportSection(
                "Risk Analysis",
                bullets=[
                    *[str(reason) for reason in readiness.get("reasons", [])],
                    *[risk.get("message", "") for risk in readiness.get("critical_risks", []) if isinstance(risk, dict)],
                    *[risk.get("message", "") for risk in readiness.get("warnings", []) if isinstance(risk, dict)],
                ]
                or ["No active release risks found in the latest computed signal."],
            ),
            ReportSection("Recommended Actions", bullets=recommendation_bullets(recommendations)),
            ReportSection("Release Gates", rows=gate_rows(readiness.get("release_gates", []))),
            ReportSection("Evidence Metrics", rows=release_metric_rows(snapshot, release_availability)),
            ReportSection(
                "Historical Trends",
                charts=self._release_historical_charts(release.release_id, snapshots, release_availability),
            ),
        ]

    def _release_summary_sections(
        self,
        session: Session,
        release: Release,
        snapshot: MetricSnapshot | None,
    ) -> list[ReportSection]:
        readiness = self._release_readiness(session, release.release_id, snapshot)
        confidence_score = readiness.get("confidence_score")
        confidence_breakdown, biggest_driver = _stored_release_confidence_artifacts(snapshot)
        release_availability = _release_metric_availability(session, release.release_id)
        if not release_availability.context.has_tickets:
            confidence_breakdown = None
            biggest_driver = None
        recommendations = (
            RecommendationEngine.build_release_recommendations(
                snapshot,
                metric_availability=release_availability,
            )
            if snapshot
            else []
        )
        outlook_section = self._release_outlook_section(session, release, snapshot, readiness)
        risk_aging_section = self._release_risk_aging_section(session, release, snapshot)
        return [
            ReportSection(
                "Executive Summary",
                lines=[readiness.get("summary") or "Release summary generated from deterministic LighthousePM metrics."],
                rows=[
                    ("Release", release.name),
                    ("Project", release.project_key),
                    ("Status", release.status or "Unknown"),
                    ("Release date", format_datetime(release.release_date)),
                    ("Latest snapshot", format_datetime(snapshot.snapshot_at if snapshot else None)),
                    ("Ruleset", _ruleset_label(snapshot)),
                ],
            ),
            outlook_section,
            risk_aging_section,
            ReportSection(
                "Confidence Score",
                rows=[
                    ("Score", format_percent(confidence_score)),
                    ("Signal", str(readiness.get("status_label") or readiness.get("signal") or "Not computed")),
                    ("Band", confidence_band(confidence_score)),
                ],
            ),
            ReportSection("Confidence Breakdown", rows=breakdown_rows(confidence_breakdown)),
            ReportSection("Biggest Driver", rows=driver_rows(biggest_driver)),
            ReportSection("Top Risks", bullets=release_top_risk_bullets(readiness, limit=3)),
            ReportSection("Top Recommendations", bullets=recommendation_bullets(recommendations, limit=3)),
            ReportSection("Decision Recommendation", lines=decision_recommendation_lines(readiness)),
        ]

    def _release_outlook_section(
        self,
        session: Session,
        release: Release,
        snapshot: MetricSnapshot | None,
        readiness: dict[str, object],
    ) -> ReportSection:
        release_gates = [
            item for item in readiness.get("release_gates", []) if isinstance(item, dict)
        ]
        critical_risks = [
            item for item in readiness.get("critical_risks", []) if isinstance(item, dict)
        ]
        warnings = [
            item for item in readiness.get("warnings", []) if isinstance(item, dict)
        ]
        last_24_hours = (
            SignalService._build_last_24_hours(
                session=session,
                release_id=release.release_id,
                latest_snapshot=snapshot,
            )
            if snapshot is not None
            else {"as_of": None, "baseline_at": None, "has_baseline": False, "items": []}
        )
        outlook = SignalService._build_release_outlook(
            release_date=release.release_date,
            latest_snapshot=snapshot,
            final_signal=(
                str(readiness["signal"]) if readiness.get("signal") in {"GREEN", "YELLOW", "RED"} else None
            ),
            confidence_score=(
                float(readiness["confidence_score"])
                if isinstance(readiness.get("confidence_score"), int | float)
                else None
            ),
            release_gates=release_gates,
            critical_risks=critical_risks,
            warnings=warnings,
            last_24_hours=last_24_hours,
        )
        active_conditions = outlook["active_conditions"]
        return ReportSection(
            "Release Outlook",
            lines=[str(outlook["disclaimer"])],
            rows=[
                ("Outlook", str(outlook["label"])),
                ("Final signal", str(outlook["signal"] or "Not computed")),
                ("Current confidence", format_percent(outlook["confidence_score"])),
                ("Passed release gates", format_number(outlook["passed_gate_count"])),
                ("Failed release gates", format_number(outlook["failed_gate_count"])),
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

    def _release_risk_aging_section(
        self,
        session: Session,
        release: Release,
        snapshot: MetricSnapshot | None,
    ) -> ReportSection:
        if snapshot is None:
            return ReportSection("Risk Aging Evidence", lines=["No release snapshot is available."])
        signal = SignalRepository.get_signal_for_snapshot(
            session=session,
            release_id=release.release_id,
            metric_snapshot_id=snapshot.id,
            ruleset_version=snapshot.ruleset_version,
        )
        evidence = signal.risk_aging_evidence if signal and signal.ruleset_version > 0 else {}
        if not evidence:
            return ReportSection(
                "Risk Aging Evidence",
                lines=["Stored risk-aging evidence is unavailable for this result."],
            )
        rows: list[tuple[str, str]] = [("Snapshot boundary", format_datetime(snapshot.snapshot_at))]
        bullets: list[str] = []
        for key, label in (("blockers", "Blockers"), ("high_severity_bugs", "High-severity bugs")):
            group = evidence.get(key, {})
            if not isinstance(group, dict):
                continue
            rows.extend(
                [
                    (f"{label} active", format_number(group.get("count"))),
                    (f"{label} known age", format_number(group.get("known_count"))),
                    (f"{label} unknown age", format_number(group.get("unknown_count"))),
                    (f"{label} oldest risk age days", format_number(group.get("oldest_age_days"))),
                    (f"{label} average risk age days", format_number(group.get("average_age_days"))),
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
            bullets=bullets or ["No active blocker or high-severity-bug aging evidence."],
        )

    def _sprint_sections(
        self,
        session: Session,
        sprint: Sprint,
        snapshot: SprintMetricSnapshot | None,
        snapshots: list[SprintMetricSnapshot],
    ) -> list[ReportSection]:
        issues = SprintRepository.list_all_sprint_issues(session=session, sprint_id=sprint.sprint_id)
        has_story_points = _sprint_confidence_available(snapshot)
        confidence_breakdown, biggest_driver = _stored_sprint_confidence_artifacts(snapshot)
        recommendations = (
            RecommendationEngine.build_sprint_recommendations(
                snapshot,
                sprint_issues=issues,
                include_story_point_rules=has_story_points,
            )
            if snapshot
            else []
        )
        delivery_confidence_score = snapshot.delivery_confidence_score if snapshot and has_story_points else None
        return [
            ReportSection(
                "Executive Summary",
                lines=["Sprint report generated from deterministic LighthousePM sprint metrics."],
                rows=[
                    ("Sprint", sprint.name),
                    ("Project", sprint.project_key),
                    ("State", sprint.state),
                    ("Start", format_datetime(sprint.start_date)),
                    ("End", format_datetime(sprint.end_date)),
                    ("Latest snapshot", format_datetime(snapshot.snapshot_at if snapshot else None)),
                    ("Ruleset", _ruleset_label(snapshot)),
                    ("Delivery confidence", format_percent(delivery_confidence_score)),
                ],
            ),
            ReportSection(
                "Delivery Confidence",
                rows=[
                    *_sprint_confidence_status_rows(snapshot),
                    ("Score", format_percent(delivery_confidence_score)),
                    ("Committed scope", format_number(snapshot.committed_scope if snapshot else None)),
                    ("Completed scope", format_percent(snapshot.completed_scope_pct if snapshot else None)),
                    ("Open blockers", format_number(snapshot.open_blockers if snapshot else None)),
                ],
                charts=[
                    ChartSpec(
                        title="Delivery Confidence Trend",
                        kind="line",
                        points=[(format_short_datetime(item.snapshot_at), item.delivery_confidence_score) for item in snapshots],
                        color=self.theme.metric_colors["sprintConfidence"].rgb,
                        y_max=100,
                        value_suffix="%",
                    )
                ] if has_story_points else [],
            ),
            ReportSection("Confidence Breakdown", rows=breakdown_rows(confidence_breakdown)),
            self._sprint_snapshot_changes(sprint.sprint_id, snapshots, has_story_points),
            ReportSection("Biggest Driver", rows=driver_rows(biggest_driver)),
            ReportSection("Velocity Health", rows=sprint_velocity_rows(snapshot, has_story_points)),
            ReportSection("Scope Stability", rows=sprint_scope_rows(snapshot, has_story_points)),
            ReportSection("Quality Signals", rows=sprint_quality_rows(snapshot)),
            ReportSection("Risk Drivers", bullets=sprint_risk_bullets(snapshot)),
            ReportSection("Recommended Actions", bullets=recommendation_bullets(recommendations)),
            ReportSection("Historical Trends", charts=self._sprint_historical_charts(snapshots, has_story_points)),
        ]

    def _sprint_summary_sections(
        self,
        session: Session,
        sprint: Sprint,
        snapshot: SprintMetricSnapshot | None,
    ) -> list[ReportSection]:
        issues = SprintRepository.list_all_sprint_issues(session=session, sprint_id=sprint.sprint_id)
        has_story_points = _sprint_confidence_available(snapshot)
        confidence_breakdown, biggest_driver = _stored_sprint_confidence_artifacts(snapshot)
        recommendations = (
            RecommendationEngine.build_sprint_recommendations(
                snapshot,
                sprint_issues=issues,
                include_story_point_rules=has_story_points,
            )
            if snapshot
            else []
        )
        delivery_confidence_score = snapshot.delivery_confidence_score if snapshot and has_story_points else None
        return [
            ReportSection(
                "Executive Summary",
                lines=["Sprint summary generated from deterministic LighthousePM sprint metrics."],
                rows=[
                    ("Sprint", sprint.name),
                    ("Project", sprint.project_key),
                    ("State", sprint.state),
                    ("Start", format_datetime(sprint.start_date)),
                    ("End", format_datetime(sprint.end_date)),
                    ("Latest snapshot", format_datetime(snapshot.snapshot_at if snapshot else None)),
                    ("Ruleset", _ruleset_label(snapshot)),
                ],
            ),
            ReportSection(
                "Delivery Confidence",
                rows=[
                    *_sprint_confidence_status_rows(snapshot),
                    ("Score", format_percent(delivery_confidence_score)),
                    ("Band", confidence_band(delivery_confidence_score)),
                    ("Committed scope", format_number(snapshot.committed_scope if snapshot else None)),
                    ("Completed scope", format_percent(snapshot.completed_scope_pct if snapshot else None)),
                ],
            ),
            ReportSection("Confidence Breakdown", rows=breakdown_rows(confidence_breakdown)),
            ReportSection("Biggest Driver", rows=driver_rows(biggest_driver)),
            ReportSection("Top Risks", bullets=sprint_top_risk_bullets(snapshot, limit=3)),
            ReportSection("Top Recommendations", bullets=recommendation_bullets(recommendations, limit=3)),
        ]

    def _release_readiness(self, session: Session, release_id: str, snapshot: MetricSnapshot | None) -> dict[str, object]:
        release_availability = _release_metric_availability(session, release_id)
        if snapshot is None:
            signal = SignalRepository.get_latest_signal(session=session, release_id=release_id)
            return {
                "signal": signal.signal if signal else None,
                "status_label": "Not computed",
                "summary": "Metrics have not been computed yet for this release.",
                "confidence_score": None,
                "reasons": signal.reasons if signal else [],
                "release_gates": [],
                "critical_risks": [],
                "warnings": [],
                "readiness_pct": None,
            }
        if not release_availability.context.has_tickets:
            return {
                "signal": None,
                "status_label": "NOT COMPUTED",
                "summary": "Release signal is not computed because no tickets are available for this scope.",
                "confidence_score": None,
                "reasons": [RELEASE_NO_TICKETS_MESSAGE],
                "release_gates": [],
                "critical_risks": [],
                "warnings": [],
                "readiness_pct": None,
            }
        signal_row = SignalRepository.get_signal_for_snapshot(
            session=session,
            release_id=release_id,
            metric_snapshot_id=snapshot.id,
            ruleset_version=snapshot.ruleset_version,
        )
        if snapshot.ruleset_version == 0:
            return {
                "signal": signal_row.signal if signal_row else None,
                "status_label": "Unversioned legacy result",
                "summary": "Legacy raw metrics are shown; derived release confidence is unavailable.",
                "confidence_score": None,
                "reasons": signal_row.reasons if signal_row else [],
                "release_gates": [],
                "critical_risks": [],
                "warnings": [],
                "readiness_pct": None,
            }
        details = dict(signal_row.readiness_evidence) if signal_row else {}
        details["release_gates"] = signal_row.release_gates if signal_row else []
        details["confidence_score"] = signal_row.confidence_score if signal_row else snapshot.confidence_score
        gates = details.get("release_gates", [])
        gate_count = len(gates) if isinstance(gates, list) else 0
        passed = sum(1 for gate in gates if isinstance(gate, dict) and gate.get("passed") is True)
        details["reasons"] = signal_row.reasons if signal_row else []
        details["readiness_pct"] = None if gate_count == 0 else round((passed / gate_count) * 100, 2)
        return details

    def _release_snapshot_changes(self, release_id: str, snapshots: list[MetricSnapshot]) -> ReportSection:
        if len(snapshots) < 2:
            return ReportSection("Snapshot Changes", lines=["No baseline snapshot is available yet."])
        if snapshots[-1].ruleset_version != snapshots[-2].ruleset_version:
            return ReportSection(
                "Snapshot Changes",
                lines=["Snapshot comparison unavailable because ruleset versions differ."],
                rows=[
                    ("Current ruleset", _ruleset_label(snapshots[-1])),
                    ("Baseline ruleset", _ruleset_label(snapshots[-2])),
                ],
            )
        if snapshots[-1].ruleset_version == 0:
            return ReportSection(
                "Snapshot Changes",
                lines=["Derived legacy release confidence is unavailable because it was not stored at calculation time."],
            )
        comparison = SnapshotComparisonService.compare_release_snapshots(
            current_snapshot=snapshots[-1],
            previous_snapshot=snapshots[-2],
        )
        return ReportSection(
            "Snapshot Changes",
            rows=[
                ("Current snapshot", format_datetime(snapshots[-1].snapshot_at)),
                ("Baseline snapshot", format_datetime(snapshots[-2].snapshot_at)),
                ("Confidence delta", format_delta(comparison.confidence_delta)),
                ("Primary driver", SnapshotComparisonService.primary_driver(comparison)),
                ("Entity", release_id),
            ],
        )

    def _release_historical_charts(
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
                    (format_short_datetime(snapshot.snapshot_at), _release_confidence_for_report(snapshot, release_availability))
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
                    (format_short_datetime(snapshot.snapshot_at), self._release_gate_passed_count(release_id, snapshot, release_availability))
                    for snapshot in snapshots
                ],
                color=self.theme.metric_colors["gatesPassed"].rgb,
            ),
            ChartSpec(
                title="Historical Open Blockers",
                kind="bar",
                points=[(format_short_datetime(snapshot.snapshot_at), snapshot.open_blockers) for snapshot in snapshots],
                color=self.theme.metric_colors["blockers"].rgb,
            ),
            ChartSpec(
                title="Historical High-Severity Bugs",
                kind="bar",
                points=[
                    (format_short_datetime(snapshot.snapshot_at), snapshot.open_high_severity_bugs)
                    for snapshot in snapshots
                ],
                color=self.theme.metric_colors["bugs"].rgb,
            ),
            ChartSpec(
                title="Historical Scope Completed",
                kind="line",
                points=[(format_short_datetime(snapshot.snapshot_at), snapshot.scope_completed_pct) for snapshot in snapshots],
                color=self.theme.metric_colors["scopeCompleted"].rgb,
                y_max=100,
                value_suffix="%",
            ),
            ChartSpec(
                title="Historical Scope Churn",
                kind="line",
                points=[(format_short_datetime(snapshot.snapshot_at), snapshot.scope_churn_7d_pct) for snapshot in snapshots],
                color=self.theme.metric_colors["scopeChurn"].rgb,
                value_suffix="%",
            ),
            ChartSpec(
                title="Historical Median Cycle Time",
                kind="line",
                points=[
                    (format_short_datetime(snapshot.snapshot_at), snapshot.median_cycle_time_days)
                    for snapshot in snapshots
                ],
                color=self.theme.metric_colors["cycleTime"].rgb,
            ),
            ChartSpec(
                title="Historical Reopen Rate",
                kind="line",
                points=[(format_short_datetime(snapshot.snapshot_at), snapshot.reopen_rate_pct) for snapshot in snapshots],
                color=self.theme.metric_colors["reopenRate"].rgb,
                y_max=100,
                value_suffix="%",
            ),
        ]

    def _release_gate_passed_count(
        self,
        release_id: str,
        snapshot: MetricSnapshot,
        release_availability: MetricAvailability | None = None,
    ) -> int | None:
        _ = release_id
        if release_availability is not None and not release_availability.context.has_tickets:
            return None
        outputs = (snapshot.calculation_provenance or {}).get("component_outputs", {})
        gates = outputs.get("release_gates", []) if isinstance(outputs, dict) else []
        if not isinstance(gates, list):
            return None
        return sum(1 for gate in gates if isinstance(gate, dict) and gate.get("passed") is True)

    def _sprint_snapshot_changes(
        self,
        sprint_id: str,
        snapshots: list[SprintMetricSnapshot],
        has_story_points: bool = True,
    ) -> ReportSection:
        if not has_story_points:
            return ReportSection("Snapshot Changes", lines=[SPRINT_STORY_POINT_UNAVAILABLE_MESSAGE])
        if len(snapshots) < 2:
            return ReportSection("Snapshot Changes", lines=["No baseline snapshot is available yet."])
        if snapshots[-1].ruleset_version != snapshots[-2].ruleset_version:
            return ReportSection(
                "Snapshot Changes",
                lines=["Snapshot comparison unavailable because ruleset versions differ."],
                rows=[
                    ("Current ruleset", _ruleset_label(snapshots[-1])),
                    ("Baseline ruleset", _ruleset_label(snapshots[-2])),
                ],
            )
        comparison = SnapshotComparisonService.compare_sprint_snapshots(
            current_snapshot=snapshots[-1],
            previous_snapshot=snapshots[-2],
        )
        return ReportSection(
            "Snapshot Changes",
            rows=[
                ("Current snapshot", format_datetime(snapshots[-1].snapshot_at)),
                ("Baseline snapshot", format_datetime(snapshots[-2].snapshot_at)),
                ("Confidence delta", format_delta(comparison.confidence_delta)),
                ("Primary driver", SnapshotComparisonService.primary_driver(comparison)),
                ("Entity", sprint_id),
            ],
        )

    def _sprint_historical_charts(
        self,
        snapshots: list[SprintMetricSnapshot],
        has_story_points: bool = True,
    ) -> list[ChartSpec]:
        story_point_charts = [
            ChartSpec(
                title="Historical Delivery Confidence",
                kind="line",
                points=[(format_short_datetime(snapshot.snapshot_at), snapshot.delivery_confidence_score) for snapshot in snapshots],
                color=self.theme.metric_colors["sprintConfidence"].rgb,
                y_max=100,
                value_suffix="%",
            ),
            ChartSpec(
                title="Historical Progress Alignment",
                kind="line",
                points=[
                    (format_short_datetime(snapshot.snapshot_at), _sprint_component(snapshot, "progress_alignment"))
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
                    (format_short_datetime(snapshot.snapshot_at), _sprint_component(snapshot, "velocity_fit"))
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
                    (format_short_datetime(snapshot.snapshot_at), _sprint_component(snapshot, "scope_stability"))
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
                    (format_short_datetime(snapshot.snapshot_at), _sprint_component(snapshot, "blocker_penalty"))
                    for snapshot in snapshots
                ],
                color=self.theme.metric_colors["blockerHealth"].rgb,
                y_max=100,
                value_suffix="%",
            ),
        ] if has_story_points else []
        ticket_count_charts = [
            ChartSpec(
                title="Historical Scope Completion",
                kind="line",
                points=[(format_short_datetime(snapshot.snapshot_at), snapshot.completed_scope_pct) for snapshot in snapshots],
                color=self.theme.metric_colors["scopeCompleted"].rgb,
                y_max=100,
                value_suffix="%",
            ),
            ChartSpec(
                title="Historical Scope Changes",
                kind="bar",
                points=[
                    (format_short_datetime(snapshot.snapshot_at), _sprint_input(snapshot, "scope_change_count"))
                    for snapshot in snapshots
                ],
                color=self.theme.metric_colors["scopeChurn"].rgb,
            ),
            ChartSpec(
                title="Historical High-Severity Bugs",
                kind="bar",
                points=[
                    (format_short_datetime(snapshot.snapshot_at), snapshot.open_high_severity_bugs)
                    for snapshot in snapshots
                ],
                color=self.theme.metric_colors["bugs"].rgb,
            ),
            ChartSpec(
                title="Historical Bugs Created During Sprint",
                kind="bar",
                points=[
                    (format_short_datetime(snapshot.snapshot_at), snapshot.bugs_created_during_sprint)
                    for snapshot in snapshots
                ],
                color=self.theme.metric_colors["confidenceWatch"].rgb,
            ),
            ChartSpec(
                title="Historical Median Cycle Time",
                kind="line",
                points=[
                    (format_short_datetime(snapshot.snapshot_at), snapshot.median_cycle_time_days)
                    for snapshot in snapshots
                ],
                color=self.theme.metric_colors["cycleTime"].rgb,
            ),
            ChartSpec(
                title="Historical Reopen Rate",
                kind="line",
                points=[(format_short_datetime(snapshot.snapshot_at), snapshot.reopen_rate_pct) for snapshot in snapshots],
                color=self.theme.metric_colors["reopenRate"].rgb,
                y_max=100,
                value_suffix="%",
            ),
        ]
        return [*story_point_charts, *ticket_count_charts]


class ReportingService:
    """Builds stakeholder PDF reports from deterministic LighthousePM data."""

    def __init__(
        self,
        template_engine: ReportTemplateEngine | None = None,
        theme_provider: PDFThemeProvider | None = None,
        chart_export_service: ChartExportService | None = None,
    ) -> None:
        self._theme_provider = theme_provider or PDFThemeProvider()
        self._theme = self._theme_provider.theme()
        self._template_engine = template_engine or ReportTemplateEngine(theme=self._theme)
        self._chart_export_service = chart_export_service or ChartExportService(theme=self._theme)

    def generate_release_report(self, session: Session, release_id: str, depth: ReportDepth) -> bytes:
        release = ReleaseRepository.get_release_by_id(session=session, release_id=release_id)
        if release is None:
            raise ValueError(f"Release '{release_id}' not found")
        generated_at = datetime.now(UTC)
        document = self._template_engine.build_release_document(session, release, depth, generated_at)
        return SimplePdfRenderer(
            generated_at=generated_at,
            version=document.version,
            theme=self._theme,
            chart_export_service=self._chart_export_service,
        ).render(document)

    def generate_sprint_report(self, session: Session, sprint_id: str, depth: ReportDepth) -> bytes:
        sprint = SprintRepository.get_sprint_by_id(session=session, sprint_id=sprint_id)
        if sprint is None:
            raise ValueError(f"Sprint '{sprint_id}' not found")
        generated_at = datetime.now(UTC)
        document = self._template_engine.build_sprint_document(session, sprint, depth, generated_at)
        return SimplePdfRenderer(
            generated_at=generated_at,
            version=document.version,
            theme=self._theme,
            chart_export_service=self._chart_export_service,
        ).render(document)

    def generate_overview_report(self, session: Session, release_id: str) -> bytes:
        release = ReleaseRepository.get_release_by_id(session=session, release_id=release_id)
        if release is None:
            raise ValueError(f"Release '{release_id}' not found")
        generated_at = datetime.now(UTC)
        document = self._template_engine.build_overview_document(session, release, generated_at)
        return SimplePdfRenderer(
            generated_at=generated_at,
            version=document.version,
            theme=self._theme,
            chart_export_service=self._chart_export_service,
        ).render(document)

    def generate_documentation_report(self) -> bytes:
        generated_at = datetime.now(UTC)
        document = self._template_engine.build_documentation_document(generated_at)
        return SimplePdfRenderer(
            generated_at=generated_at,
            version=document.version,
            theme=self._theme,
            chart_export_service=self._chart_export_service,
        ).render(document)


def _read_about_documentation() -> str:
    for path in _about_documentation_paths():
        if path.exists():
            return path.read_text(encoding="utf-8")
    raise ValueError("ABOUT.md documentation was not found")


def _about_documentation_paths() -> list[Path]:
    bundled_root = Path(getattr(sys, "_MEIPASS", ""))
    service_path = Path(__file__).resolve()
    return [
        bundled_root / "ABOUT.md",
        service_path.parents[3] / "ABOUT.md",
        Path.cwd() / "ABOUT.md",
        Path.cwd().parent / "ABOUT.md",
    ]


def _documentation_sections_from_markdown(markdown: str) -> tuple[str, list[ReportSection]]:
    document_title = "Lighthouse PM Documentation"
    sections: list[ReportSection] = []
    current_title: str | None = None
    current_lines: list[str] = []
    current_bullets: list[str] = []
    current_heading_color: tuple[float, float, float] | None = None
    current_include_empty = False
    current_page = ""

    def flush_section() -> None:
        nonlocal current_title, current_lines, current_bullets, current_heading_color, current_include_empty
        if current_title and (current_lines or current_bullets or current_include_empty):
            sections.append(
                ReportSection(
                    title=current_title,
                    lines=current_lines,
                    bullets=current_bullets,
                    heading_color=current_heading_color,
                )
            )
        current_title = None
        current_lines = []
        current_bullets = []
        current_heading_color = None
        current_include_empty = False

    for raw_line in markdown.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("# "):
            document_title = line[2:].strip()
            continue
        if line.startswith("## "):
            flush_section()
            current_page = line[3:].strip()
            current_title = current_page
            current_heading_color = _documentation_heading_color(current_page)
            current_include_empty = True
            continue
        if line.startswith("### "):
            flush_section()
            heading = line[4:].strip()
            current_title = heading
            current_heading_color = _documentation_heading_color(current_page)
            continue
        if line.startswith("#### "):
            flush_section()
            heading = line[5:].strip()
            current_title = heading
            current_heading_color = _documentation_heading_color(current_page)
            continue
        if line.startswith("- "):
            current_bullets.append(line[2:].strip())
            continue
        if "." in line:
            number, text = line.split(".", 1)
            if number.isdigit() and text.startswith(" "):
                current_bullets.append(text.strip())
                continue
        current_lines.append(line)

    flush_section()
    return document_title, sections


def _documentation_heading_color(page: str) -> tuple[float, float, float] | None:
    colors = {
        "Overview": "#4b22d4",
        "Releases": "#0b6bcb",
        "Sprints": "#237445",
    }
    color = colors.get(page)
    return pdf_color(color).rgb if color else None


def application_version() -> str:
    try:
        return metadata.version("jira-release-signals-backend")
    except metadata.PackageNotFoundError:
        pyproject = Path(__file__).resolve().parents[2] / "pyproject.toml"
        if pyproject.exists():
            with pyproject.open("rb") as handle:
                return str(tomllib.load(handle)["project"]["version"])
        return "0.0.0"


def pdf_color(hex_value: str) -> PdfColor:
    normalized = hex_value.strip().lstrip("#")
    if len(normalized) != 6:
        raise ValueError(f"Invalid PDF color '{hex_value}'")
    red = int(normalized[0:2], 16) / 255
    green = int(normalized[2:4], 16) / 255
    blue = int(normalized[4:6], 16) / 255
    return PdfColor(hex=f"#{normalized.lower()}", rgb=(red, green, blue))


def _pdf_rgb(color: tuple[float, float, float]) -> str:
    return " ".join(f"{component:.6f}".rstrip("0").rstrip(".") for component in color)


def format_datetime(value: datetime | None) -> str:
    if value is None:
        return "N/A"
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).strftime("%Y-%m-%d %H:%M UTC")


def format_short_datetime(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).strftime("%m-%d %H:%M")


def format_percent(value: object) -> str:
    if not isinstance(value, int | float):
        return "N/A"
    return f"{round(float(value), 2)}%"


def format_number(value: object) -> str:
    if not isinstance(value, int | float):
        return "N/A"
    if float(value).is_integer():
        return str(int(value))
    return str(round(float(value), 2))


def format_delta(value: float) -> str:
    if value == 0:
        return "0%"
    return f"{'+' if value > 0 else ''}{round(value, 2)}%"


def confidence_band(value: object) -> str:
    if not isinstance(value, int | float):
        return "Not computed"
    if value >= 91:
        return "High Confidence"
    if value >= 61:
        return "Medium Confidence"
    return "Low Confidence"


def breakdown_rows(breakdown) -> list[tuple[str, str]]:
    if breakdown is None:
        return [("Status", "No confidence breakdown available.")]
    rows = [("Total score", format_percent(breakdown.totalScore))]
    rows.extend(
        (component.name, f"{format_percent(component.score)} of {format_percent(component.maxScore)} | {component.status} | {component.explanation}")
        for component in breakdown.components
    )
    return rows


def driver_rows(driver) -> list[tuple[str, str]]:
    if driver is None:
        return [("Status", "No biggest driver is available.")]
    return [
        ("Title", driver.title),
        ("Category", driver.category),
        ("Impact", format_percent(driver.impact)),
        ("Contribution", format_percent(driver.contributionPercent)),
        ("Explanation", driver.explanation),
        ("Recommendation", driver.recommendation),
    ]


def recommendation_bullets(recommendations, limit: int | None = None) -> list[str]:
    if not recommendations:
        return ["No deterministic recommended actions are active for this snapshot."]
    selected_recommendations = recommendations if limit is None else recommendations[:limit]
    return [
        f"P{item.priority} {item.title}: {item.description} Confidence impact {item.confidenceImpact}%, effort {item.effort}, category {item.category}."
        for item in selected_recommendations
    ]


def release_top_risk_bullets(readiness: dict[str, object], limit: int) -> list[str]:
    risks: list[str] = []
    for key in ("critical_risks", "warnings"):
        items = readiness.get(key, [])
        if not isinstance(items, list):
            continue
        for item in items:
            if isinstance(item, dict) and item.get("message"):
                risks.append(str(item["message"]))
    reasons = readiness.get("reasons", [])
    if isinstance(reasons, list):
        risks.extend(str(reason) for reason in reasons)
    deduped = list(dict.fromkeys(risks))
    return deduped[:limit] or ["No active top release risks found in the latest computed signal."]


def decision_recommendation_lines(readiness: dict[str, object]) -> list[str]:
    signal = str(readiness.get("signal") or "").upper()
    if signal == "GREEN":
        return ["Release can proceed from the current deterministic risk posture. Continue monitoring gates and confidence before final approval."]
    if signal == "YELLOW":
        return ["Proceed only with named mitigation owners for the top risks. Recheck confidence after recommended actions are completed."]
    if signal == "RED":
        return ["Do not release until red-level risks are resolved and a fresh LighthousePM snapshot confirms improved confidence."]
    return ["Do not make a release decision until release metrics and signal have been computed."]


def _overview_release_snapshot_label(snapshot: MetricSnapshot | None) -> str:
    return format_datetime(snapshot.snapshot_at) if snapshot else "No snapshot available yet."


def _overview_sprint_snapshot_label(sprint: Sprint | None, snapshot: SprintMetricSnapshot | None) -> str:
    if sprint is None:
        return "No sprint snapshot available yet."
    return format_datetime(snapshot.snapshot_at) if snapshot else "No sprint snapshot available yet."


def overview_sprint_metric_rows(
    sprint: Sprint | None,
    snapshot: SprintMetricSnapshot | None,
    has_story_points: bool = True,
) -> list[tuple[str, str]]:
    if sprint is None:
        return [("Status", "No active sprint is available for the overview dashboard.")]
    if snapshot is None:
        return [
            ("Sprint", sprint.name),
            ("State", sprint.state),
            ("Status", "No sprint snapshot available yet."),
        ]
    rows = [
        ("Sprint", sprint.name),
        ("State", sprint.state),
        ("Goal", sprint.goal or "N/A"),
        ("Start", format_datetime(sprint.start_date)),
        ("End", format_datetime(sprint.end_date)),
        ("Committed scope", format_number(snapshot.committed_scope if snapshot else None)),
        ("Completed scope", format_percent(snapshot.completed_scope_pct if snapshot else None)),
        ("Open blockers", format_number(snapshot.open_blockers if snapshot else None)),
        ("High severity bugs", format_number(snapshot.open_high_severity_bugs if snapshot else None)),
    ]
    if has_story_points:
        rows.append(("Delivery confidence", format_percent(snapshot.delivery_confidence_score if snapshot else None)))
    else:
        rows.append(("Story-point metrics", SPRINT_STORY_POINT_UNAVAILABLE_MESSAGE))
    return rows


def overview_risk_bullets(
    readiness: dict[str, object],
    snapshot: MetricSnapshot | None,
    sprint_snapshot: SprintMetricSnapshot | None,
) -> list[str]:
    bullets = release_top_risk_bullets(readiness, limit=5)
    if snapshot is not None:
        bullets.extend(
            [
                f"Release blockers: {snapshot.open_blockers}.",
                f"Release high-severity bugs: {snapshot.open_high_severity_bugs}.",
                f"Release scope churn: {format_percent(snapshot.scope_churn_7d_pct)}.",
            ]
        )
    if sprint_snapshot is not None:
        bullets.extend(
            [
                f"Sprint blockers: {sprint_snapshot.open_blockers}.",
                f"Sprint high-severity bugs: {sprint_snapshot.open_high_severity_bugs}.",
                f"Sprint bugs created during sprint: {sprint_snapshot.bugs_created_during_sprint}.",
            ]
        )
    return list(dict.fromkeys(bullets)) or ["No active overview risk indicators found."]


def overview_signal_rows(readiness: dict[str, object]) -> list[tuple[str, str]]:
    reasons = readiness.get("reasons", [])
    reason_text = ", ".join(str(reason) for reason in reasons) if isinstance(reasons, list) else "N/A"
    return [
        ("Signal", str(readiness.get("signal") or "Not computed")),
        ("Status", str(readiness.get("status_label") or "Not computed")),
        ("Confidence", format_percent(readiness.get("confidence_score"))),
        ("Readiness", format_percent(readiness.get("readiness_pct"))),
        ("Reasons", reason_text or "No signal reasons recorded."),
    ]


def overview_health_rows(
    readiness: dict[str, object],
    snapshot: MetricSnapshot | None,
    sprint_snapshot: SprintMetricSnapshot | None,
    sprint_has_story_points: bool = True,
) -> list[tuple[str, str]]:
    gates = readiness.get("release_gates", [])
    gate_count = len(gates) if isinstance(gates, list) else 0
    gates_passed = sum(1 for gate in gates if isinstance(gate, dict) and gate.get("passed") is True)
    return [
        ("Release gates passed", f"{gates_passed} of {gate_count}" if gate_count else "N/A"),
        ("Release confidence band", confidence_band(readiness.get("confidence_score"))),
        ("Release scope completed", format_percent(snapshot.scope_completed_pct if snapshot else None)),
        ("Release cycle time", format_number(snapshot.median_cycle_time_days if snapshot else None)),
        (
            "Sprint delivery band",
            confidence_band(
                sprint_snapshot.delivery_confidence_score
                if sprint_snapshot and sprint_has_story_points
                else None
            ),
        ),
        ("Sprint completed scope", format_percent(sprint_snapshot.completed_scope_pct if sprint_snapshot else None)),
        ("Sprint reopen rate", format_percent(sprint_snapshot.reopen_rate_pct if sprint_snapshot else None)),
    ]


def overview_recommendation_bullets(release_recommendations, sprint_recommendations) -> list[str]:
    bullets = [
        f"Release: {item}" for item in recommendation_bullets(release_recommendations, limit=3)
    ]
    if sprint_recommendations:
        bullets.extend(f"Sprint: {item}" for item in recommendation_bullets(sprint_recommendations, limit=3))
    return bullets or ["No deterministic recommendations are active for the overview dashboard."]


def _sprint_confidence_available(snapshot: SprintMetricSnapshot | None) -> bool:
    return bool(
        snapshot
        and snapshot.delivery_confidence_status in {"PARTIAL", "COMPUTED"}
        and snapshot.delivery_confidence_score is not None
    )


def _sprint_confidence_status_rows(
    snapshot: SprintMetricSnapshot | None,
) -> list[tuple[str, str]]:
    if snapshot is None:
        return [("Status", "Delivery confidence has not been computed yet.")]
    rows = [
        ("Status", snapshot.delivery_confidence_status.replace("_", " ").title()),
        ("Story-point coverage", format_percent(snapshot.story_point_coverage_pct)),
    ]
    rows.extend(
        ("Explanation" if index == 0 else "Coverage guidance", explanation)
        for index, explanation in enumerate(snapshot.delivery_confidence_explanations)
    )
    return rows


def _first_last_delta(values: list[float | None]) -> float | None:
    numeric_values = [float(value) for value in values if isinstance(value, int | float)]
    if len(numeric_values) < 2:
        return None
    return numeric_values[-1] - numeric_values[0]


def _release_confidence_for_report(
    snapshot: MetricSnapshot,
    release_availability: MetricAvailability | None = None,
) -> float | None:
    if release_availability is not None and not release_availability.context.has_tickets:
        return None
    return SignalService._confidence_score_for_snapshot(snapshot)


def _stored_release_confidence_artifacts(
    snapshot: MetricSnapshot | None,
) -> tuple[ConfidenceBreakdown | None, DriverAnalysis | None]:
    if snapshot is None or snapshot.ruleset_version == 0:
        return None, None
    outputs = (snapshot.calculation_provenance or {}).get("component_outputs", {})
    if not isinstance(outputs, dict):
        return None, None
    breakdown = outputs.get("confidence_breakdown")
    driver = outputs.get("biggest_driver")
    return (
        ConfidenceBreakdown.model_validate(breakdown) if isinstance(breakdown, dict) else None,
        DriverAnalysis.model_validate(driver) if isinstance(driver, dict) else None,
    )


def _stored_sprint_confidence_artifacts(
    snapshot: SprintMetricSnapshot | None,
) -> tuple[ConfidenceBreakdown | None, DriverAnalysis | None]:
    if snapshot is None or snapshot.ruleset_version == 0:
        return None, None
    outputs = (snapshot.calculation_provenance or {}).get("component_outputs", {})
    if not isinstance(outputs, dict):
        return None, None
    breakdown = outputs.get("confidence_breakdown")
    driver = outputs.get("biggest_driver")
    return (
        ConfidenceBreakdown.model_validate(breakdown) if isinstance(breakdown, dict) else None,
        DriverAnalysis.model_validate(driver) if isinstance(driver, dict) else None,
    )


def _ruleset_label(snapshot: MetricSnapshot | SprintMetricSnapshot | None) -> str:
    if snapshot is None:
        return "N/A"
    if snapshot.ruleset_version == 0:
        return "Unversioned legacy result (v0)"
    return f"Ruleset v{snapshot.ruleset_version}"


def gate_rows(gates: object) -> list[tuple[str, str]]:
    if not isinstance(gates, list) or not gates:
        return [("Status", "No release gates available.")]
    rows: list[tuple[str, str]] = []
    for gate in gates:
        if not isinstance(gate, dict):
            continue
        state = "Passed" if gate.get("passed") else "Not passed"
        rows.append(
            (
                str(gate.get("label") or gate.get("metric_name") or "Gate"),
                f"{state} | value {format_number(gate.get('value'))} {gate.get('comparison', '')} {format_number(gate.get('threshold'))}",
            )
        )
    return rows or [("Status", "No release gates available.")]


def release_metric_rows(
    snapshot: MetricSnapshot | None,
    availability: MetricAvailability | None = None,
) -> list[tuple[str, str]]:
    if snapshot is None:
        return [("Status", "No release metrics have been computed yet.")]
    rows = []
    if availability is not None and not availability.context.has_tickets:
        rows.append(("Status", RELEASE_NO_TICKETS_MESSAGE))
    rows.extend(
        [
            ("Open blockers", _release_metric_value(snapshot, availability, "open_blockers", format_number)),
            (
                "Open high-severity bugs",
                _release_metric_value(snapshot, availability, "open_high_severity_bugs", format_number),
            ),
            ("Scope completed", _release_metric_value(snapshot, availability, "scope_completed_pct", format_percent)),
            ("Completed tickets", _release_metric_value(snapshot, availability, "completed_tickets", format_number)),
            ("Scope churn 7d", _release_metric_value(snapshot, availability, "scope_churn_7d_pct", format_percent)),
            ("Scope added 7d", _release_metric_value(snapshot, availability, "scope_added_7d_count", format_number)),
            ("Scope removed 7d", _release_metric_value(snapshot, availability, "scope_removed_7d_count", format_number)),
            (
                "Median cycle time",
                _release_metric_value(
                    snapshot,
                    availability,
                    "median_cycle_time_days",
                    lambda value: f"{format_number(value)} days",
                ),
            ),
            ("Reopen rate", _release_metric_value(snapshot, availability, "reopen_rate_pct", format_percent)),
        ]
    )
    if availability is not None and availability.context.has_tickets and not availability.context.has_story_points:
        rows.append(("Story-point metrics", f"N/A | {RELEASE_NO_STORY_POINTS_MESSAGE}"))
    return rows


def _release_metric_value(
    snapshot: MetricSnapshot,
    availability: MetricAvailability | None,
    metric_name: str,
    formatter,
) -> str:
    item = availability.metrics.get(metric_name) if availability is not None else None
    if item is not None and not item.available:
        return f"N/A | {item.reason or 'Metric is unavailable.'}"
    return formatter(getattr(snapshot, metric_name))


def sprint_velocity_rows(snapshot: SprintMetricSnapshot | None, has_story_points: bool = True) -> list[tuple[str, str]]:
    if not has_story_points:
        return [("Status", SPRINT_STORY_POINT_UNAVAILABLE_MESSAGE)]
    if snapshot is None or not snapshot.delivery_confidence_inputs:
        return [("Status", "No velocity baseline is available.")]
    inputs = snapshot.delivery_confidence_inputs
    historical = inputs.get("historical_velocity")
    completed = inputs.get("completed_effective_points")
    velocity_health = None
    if isinstance(historical, int | float) and historical > 0 and isinstance(completed, int | float):
        velocity_health = round((completed / historical) * 100, 2)
    return [
        ("Historical velocity", format_number(historical)),
        ("Completed effective points", format_number(completed)),
        ("Velocity health", format_percent(velocity_health)),
        ("Baseline sprint count", format_number(inputs.get("baseline_sprint_count"))),
    ]


def sprint_scope_rows(snapshot: SprintMetricSnapshot | None, has_story_points: bool = True) -> list[tuple[str, str]]:
    if not has_story_points:
        return [("Status", SPRINT_STORY_POINT_UNAVAILABLE_MESSAGE)]
    if snapshot is None or not snapshot.delivery_confidence_inputs:
        return [("Status", "No scope stability data is available.")]
    inputs = snapshot.delivery_confidence_inputs
    index = inputs.get("scope_stability_index")
    return [
        ("Scope stability component", format_percent((snapshot.delivery_confidence_components or {}).get("scope_stability"))),
        ("Scope stability index", format_percent(index * 100 if isinstance(index, int | float) else None)),
        ("Added issues", format_number(inputs.get("scope_added_count"))),
        ("Removed issues", format_number(inputs.get("scope_removed_count"))),
        ("Scope change count", format_number(inputs.get("scope_change_count"))),
    ]


def sprint_quality_rows(snapshot: SprintMetricSnapshot | None) -> list[tuple[str, str]]:
    if snapshot is None:
        return [("Status", "No sprint quality metrics have been computed yet.")]
    return [
        ("Open high-severity bugs", format_number(snapshot.open_high_severity_bugs)),
        ("Bugs created during sprint", format_number(snapshot.bugs_created_during_sprint)),
        ("Reopen rate", format_percent(snapshot.reopen_rate_pct)),
        ("Median cycle time", f"{format_number(snapshot.median_cycle_time_days)} days"),
    ]


def sprint_risk_bullets(snapshot: SprintMetricSnapshot | None) -> list[str]:
    if snapshot is None:
        return ["No sprint risk metrics have been computed yet."]
    bullets: list[str] = []
    if snapshot.open_blockers > 0:
        bullets.append(f"{snapshot.open_blockers} open blockers require attention.")
    if snapshot.open_high_severity_bugs > 0:
        bullets.append(f"{snapshot.open_high_severity_bugs} open high-severity bugs add quality risk.")
    if snapshot.rollover_count > 0:
        bullets.append(f"{snapshot.rollover_count} rollover issues indicate delivery risk.")
    return bullets or ["No blocker, high-severity bug, or rollover risk is active in this snapshot."]


def sprint_top_risk_bullets(snapshot: SprintMetricSnapshot | None, limit: int) -> list[str]:
    return sprint_risk_bullets(snapshot)[:limit]


def _sprint_component(snapshot: SprintMetricSnapshot, key: str) -> float | None:
    if snapshot.delivery_confidence_components is None:
        return None
    value = snapshot.delivery_confidence_components.get(key)
    return float(value) if isinstance(value, int | float) else None


def _sprint_input(snapshot: SprintMetricSnapshot, key: str) -> float | None:
    if snapshot.delivery_confidence_inputs is None:
        return None
    value = snapshot.delivery_confidence_inputs.get(key)
    return float(value) if isinstance(value, int | float) else None


class _RasterCanvas:
    def __init__(self, width: int, height: int, background: tuple[int, int, int]) -> None:
        self.width = width
        self.height = height
        self._data = bytearray(background * (width * height))

    def bytes(self) -> bytes:
        return bytes(self._data)

    def set_pixel(self, x: int, y: int, color: tuple[int, int, int]) -> None:
        if x < 0 or y < 0 or x >= self.width or y >= self.height:
            return
        index = (y * self.width + x) * 3
        self._data[index : index + 3] = bytes(color)

    def fill_rect(self, x: int, y: int, width: int, height: int, color: tuple[int, int, int]) -> None:
        if width <= 0 or height <= 0:
            return
        left = max(0, x)
        right = min(self.width, x + width)
        top = max(0, y)
        bottom = min(self.height, y + height)
        row = bytes(color) * max(0, right - left)
        for py in range(top, bottom):
            start = (py * self.width + left) * 3
            self._data[start : start + len(row)] = row

    def rect(
        self,
        x: int,
        y: int,
        width: int,
        height: int,
        outline: tuple[int, int, int],
    ) -> None:
        self.line(x, y, x + width, y, outline)
        self.line(x, y + height, x + width, y + height, outline)
        self.line(x, y, x, y + height, outline)
        self.line(x + width, y, x + width, y + height, outline)

    def line(
        self,
        x1: int,
        y1: int,
        x2: int,
        y2: int,
        color: tuple[int, int, int],
        width: int = 1,
    ) -> None:
        dx = abs(x2 - x1)
        dy = -abs(y2 - y1)
        sx = 1 if x1 < x2 else -1
        sy = 1 if y1 < y2 else -1
        error = dx + dy
        x = x1
        y = y1
        radius = max(0, width // 2)
        while True:
            self.fill_rect(x - radius, y - radius, width, width, color)
            if x == x2 and y == y2:
                break
            error2 = 2 * error
            if error2 >= dy:
                error += dy
                x += sx
            if error2 <= dx:
                error += dx
                y += sy

    def circle(self, x: int, y: int, radius: int, color: tuple[int, int, int]) -> None:
        for py in range(y - radius, y + radius + 1):
            for px in range(x - radius, x + radius + 1):
                if (px - x) ** 2 + (py - y) ** 2 <= radius**2:
                    self.set_pixel(px, py, color)


def _rgb255(color: tuple[float, float, float]) -> tuple[int, int, int]:
    return tuple(max(0, min(255, round(component * 255))) for component in color)


def _chart_y(value: float, max_value: float, plot_top: int, plot_bottom: int) -> int:
    return plot_bottom - round((value / max_value) * (plot_bottom - plot_top))


def _chart_max_value(chart: ChartSpec, values: list[tuple[str, float]]) -> float:
    numeric_values = [float(value) for _, value in values]
    return max(chart.y_max or max(max(numeric_values), 1.0), 1.0)


def _format_scale_value(value: float, suffix: str) -> str:
    numeric_value = float(value)
    if numeric_value.is_integer():
        formatted = str(int(numeric_value))
    else:
        formatted = str(round(numeric_value, 2))
    return f"{formatted}{suffix}"


def _format_number(value: float) -> str:
    return str(int(value)) if value.is_integer() else str(round(value, 1))


def _wrap(value: str, width: int) -> list[str]:
    words = str(value).split()
    if not words:
        return [""]
    lines: list[str] = []
    current = words[0]
    for word in words[1:]:
        if len(current) + len(word) + 1 <= width:
            current = f"{current} {word}"
        else:
            lines.append(current)
            current = word
    lines.append(current)
    return lines


def _pdf_escape(value: str) -> str:
    return str(value).replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _build_pdf(pages: list[list[str]]) -> bytes:
    objects: list[bytes] = []
    objects.append(b"<< /Type /Catalog /Pages 2 0 R >>")
    kids = " ".join(f"{5 + index * 2} 0 R" for index in range(len(pages)))
    objects.append(f"<< /Type /Pages /Kids [{kids}] /Count {len(pages)} >>".encode())
    objects.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    objects.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold >>")
    for index, content in enumerate(pages):
        page_object_id = 5 + index * 2
        stream_object_id = page_object_id + 1
        page = (
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            f"/Resources << /Font << /F1 3 0 R /F2 4 0 R >> >> /Contents {stream_object_id} 0 R >>"
        )
        stream = "\n".join(content).encode("latin-1", errors="replace")
        objects.append(page.encode())
        objects.append(b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream")

    output = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for object_id, body in enumerate(objects, start=1):
        offsets.append(len(output))
        output.extend(f"{object_id} 0 obj\n".encode())
        output.extend(body)
        output.extend(b"\nendobj\n")
    xref_at = len(output)
    output.extend(f"xref\n0 {len(objects) + 1}\n".encode())
    output.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        output.extend(f"{offset:010d} 00000 n \n".encode())
    output.extend(
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref_at}\n%%EOF\n".encode()
    )
    return bytes(output)
